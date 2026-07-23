#!/usr/bin/env node
/**
 * ingest-sanctions.mjs
 * Authoritative sanctions data pipeline.
 *
 * Fetches from OFAC SDN + Consolidated (and probes EU/UK/UN).
 * Outputs shared/sanctions-list.json (gitignored, ~17MB)
 * and shared/sanctions-list.sample.json (10 real entities, committed).
 *
 * Usage: node scripts/ingest-sanctions.mjs
 */

import fs from "node:fs";
import https from "node:https";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, "..");
const SHARED_DIR = path.join(SKILL_ROOT, "shared");
const OUT_PATH = path.join(SHARED_DIR, "sanctions-list.json");
const SAMPLE_PATH = path.join(SHARED_DIR, "sanctions-list.sample.json");

const SOURCES = {
  "OFAC-SDN": {
    url: "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
    format: "xml",
    required: true,
  },
  "OFAC-CONS": {
    url: "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/CONS_PRIM.XML",
    format: "xml",
    required: false,
  },
  "EU-FSF": {
    // NOTE: token is a public download token, not a secret. It can be overridden
    // via env var EU_SANCTIONS_TOKEN if the EU rotates it.
    url: `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=${process.env.EU_SANCTIONS_TOKEN || "dG9rZW5hcHBsaWNhdGlvbjE"}`,
    format: "xml",
    required: false,
  },
  "UK-OFSI": {
    url: "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/consolidated_list.csv",
    format: "csv",
    required: false,
  },
  "UN-SC": {
    url: "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    format: "xml",
    required: false,
  },
};

/**
 * Fetch a URL, following redirects up to maxRedirects times.
 * Returns { body: string, finalUrl: string } or throws.
 */
function fetchUrl(urlStr, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    function doFetch(urlStr, redirectsLeft) {
      const url = new URL(urlStr);
      const lib = url.protocol === "https:" ? https : http;
      const options = {
        hostname: url.hostname,
        port: url.port || (url.protocol === "https:" ? 443 : 80),
        path: url.pathname + url.search,
        method: "GET",
        headers: {
          "User-Agent": "LynAI-SanctionsIngest/1.0 (compliance data pipeline)",
          "Accept": "application/xml, text/xml, */*",
        },
        timeout: 120000, // 2 min timeout for large files
      };
      const req = lib.request(options, (res) => {
        if ([301, 302, 303, 307, 308].includes(res.statusCode)) {
          if (redirectsLeft <= 0) {
            reject(new Error(`Too many redirects from ${urlStr}`));
            return;
          }
          const location = res.headers["location"];
          if (!location) {
            reject(new Error(`Redirect with no Location header from ${urlStr}`));
            return;
          }
          const nextUrl = new URL(location, urlStr).toString();
          res.resume();
          doFetch(nextUrl, redirectsLeft - 1);
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode} from ${urlStr}`));
          return;
        }
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => resolve({ body: Buffer.concat(chunks).toString("utf8"), finalUrl: urlStr }));
        res.on("error", reject);
      });
      req.on("timeout", () => {
        req.destroy();
        reject(new Error(`Request timed out for ${urlStr}`));
      });
      req.on("error", reject);
      req.end();
    }
    doFetch(urlStr, maxRedirects);
  });
}

/**
 * Parse OFAC SDN/CONS XML.
 * Structure: <sdnList><publshInformation><Publish_Date>MM/DD/YYYY</Publish_Date>...
 * Returns { publishDate, entities[] }
 */
function parseOfacXml(xmlBody, sourceKey) {
  const sourceUrl = SOURCES[sourceKey]?.url || "";

  // Extract publication date from publshInformation > Publish_Date (note OFAC's misspelling "publshInformation")
  let publishDate = "unknown";
  const publshInfoMatch = xmlBody.match(/<publshInformation>([\s\S]*?)<\/publshInformation>/i);
  if (publshInfoMatch) {
    const publishDateMatch = publshInfoMatch[1].match(/<Publish_Date>([\d\/]+)<\/Publish_Date>/i);
    if (publishDateMatch) {
      // Convert MM/DD/YYYY to ISO format YYYY-MM-DD
      const [month, day, year] = publishDateMatch[1].split("/");
      publishDate = `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
    }
  }

  const entities = [];

  // Extract all sdnEntry blocks
  const entryRe = /<sdnEntry>([\s\S]*?)<\/sdnEntry>/gi;
  let entryMatch;

  while ((entryMatch = entryRe.exec(xmlBody)) !== null) {
    const entry = entryMatch[1];

    // Extract uid
    const uidMatch = entry.match(/<uid>(\d+)<\/uid>/i);
    const uid = uidMatch ? uidMatch[1] : null;
    if (!uid) continue;

    // Extract primary name (lastName is the primary field for orgs; firstName for individuals)
    const lastNameMatch = entry.match(/<lastName>([\s\S]*?)<\/lastName>/i);
    const firstNameMatch = entry.match(/<firstName>([\s\S]*?)<\/firstName>/i);
    const sdnTypeMatch = entry.match(/<sdnType>([\s\S]*?)<\/sdnType>/i);

    if (!lastNameMatch) continue;

    const lastName = decodeXmlEntities(lastNameMatch[1].trim());
    const firstName = firstNameMatch ? decodeXmlEntities(firstNameMatch[1].trim()) : "";
    const sdnType = sdnTypeMatch ? sdnTypeMatch[1].trim() : "Unknown";

    // Primary name: for individuals "First Last", for entities just lastName
    const primaryName = (sdnType === "Individual" && firstName)
      ? `${firstName} ${lastName}`
      : lastName;

    if (!primaryName || primaryName.length < 2) continue;

    // Extract aliases (akaList → aka entries)
    const aliases = [];
    const akaListMatch = entry.match(/<akaList>([\s\S]*?)<\/akaList>/i);
    if (akaListMatch) {
      const akaRe = /<aka>([\s\S]*?)<\/aka>/gi;
      let akaMatch;
      while ((akaMatch = akaRe.exec(akaListMatch[1])) !== null) {
        const akaEntry = akaMatch[1];
        const akaLastMatch = akaEntry.match(/<lastName>([\s\S]*?)<\/lastName>/i);
        const akaFirstMatch = akaEntry.match(/<firstName>([\s\S]*?)<\/firstName>/i);
        if (akaLastMatch) {
          const akaLast = decodeXmlEntities(akaLastMatch[1].trim());
          const akaFirst = akaFirstMatch ? decodeXmlEntities(akaFirstMatch[1].trim()) : "";
          const aliasName = (akaFirst && akaFirst !== akaLast) ? `${akaFirst} ${akaLast}` : akaLast;
          if (aliasName && aliasName !== primaryName && !aliases.includes(aliasName)) {
            aliases.push(aliasName);
          }
        }
      }
    }

    // Extract program
    const programMatch = entry.match(/<program>([\s\S]*?)<\/program>/i);
    const program = programMatch ? decodeXmlEntities(programMatch[1].trim()) : "UNKNOWN";

    entities.push({
      name: primaryName,
      aliases,
      program,
      source: sourceKey,
      source_url: sourceUrl,
      source_publish_date: publishDate,
      source_record_uid: `${sourceKey}-${uid}`,
      retrieved_at: new Date().toISOString(),
    });
  }

  return { publishDate, entities };
}

function decodeXmlEntities(str) {
  return str
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)));
}

async function probeSource(key, sourceConfig) {
  console.log(`  Probing ${key}: ${sourceConfig.url.substring(0, 80)}...`);
  try {
    const { body, finalUrl } = await fetchUrl(sourceConfig.url);
    const firstBytes = body.substring(0, 200);
    const hasXmlContent = firstBytes.includes("<?xml") || firstBytes.includes("<") ;
    const hasContent = body.length > 1000;
    if (hasContent && (sourceConfig.format !== "xml" || hasXmlContent)) {
      console.log(`  ${key}: REACHABLE (${Math.round(body.length / 1024)}KB)`);
      return { status: "OK", body, finalUrl };
    } else {
      console.log(`  ${key}: Response too short or unexpected format (${body.length} bytes)`);
      return { status: "PENDING", reason: `response-too-short-or-unexpected: ${body.length} bytes` };
    }
  } catch (err) {
    console.log(`  ${key}: UNREACHABLE — ${err.message}`);
    return { status: "PENDING", reason: err.message };
  }
}

async function main() {
  console.log("=== LynAI Sanctions Ingest Pipeline ===");
  console.log(`Output: ${OUT_PATH}`);
  console.log(`Started: ${new Date().toISOString()}\n`);

  // Ensure shared dir exists
  if (!fs.existsSync(SHARED_DIR)) {
    fs.mkdirSync(SHARED_DIR, { recursive: true });
  }

  const allEntities = [];
  const sourceMeta = {};
  const seenUids = new Set();

  // === OFAC SDN (required) ===
  console.log("Fetching OFAC SDN...");
  let ofacSdnPublishDate = "unknown";
  try {
    const { body } = await fetchUrl(SOURCES["OFAC-SDN"].url);
    console.log(`  Downloaded ${Math.round(body.length / 1024 / 1024 * 10) / 10}MB`);
    const { publishDate, entities } = parseOfacXml(body, "OFAC-SDN");
    ofacSdnPublishDate = publishDate;
    console.log(`  Parsed ${entities.length} entries (publish date: ${publishDate})`);
    let added = 0;
    for (const e of entities) {
      const uid = e.source_record_uid;
      if (!seenUids.has(uid)) {
        seenUids.add(uid);
        allEntities.push(e);
        added++;
      }
    }
    console.log(`  Added ${added} unique OFAC-SDN entities`);
    sourceMeta["OFAC-SDN"] = {
      source_url: SOURCES["OFAC-SDN"].url,
      publish_date: publishDate,
      record_count: entities.length,
      retrieved_at: new Date().toISOString(),
      status: "OK",
    };
  } catch (err) {
    console.error(`  OFAC-SDN FETCH FAILED: ${err.message}`);
    // Try curl fallback
    console.log("  Trying curl fallback for OFAC-SDN...");
    try {
      const { spawnSync } = await import("node:child_process");
      const result = spawnSync("curl", [
        "-L", "-s", "--max-time", "120",
        "-o", path.join(SHARED_DIR, "_ofac_sdn_tmp.xml"),
        SOURCES["OFAC-SDN"].url
      ], { encoding: "buffer", timeout: 130000 });
      if (result.status === 0 && fs.existsSync(path.join(SHARED_DIR, "_ofac_sdn_tmp.xml"))) {
        const body = fs.readFileSync(path.join(SHARED_DIR, "_ofac_sdn_tmp.xml"), "utf8");
        fs.unlinkSync(path.join(SHARED_DIR, "_ofac_sdn_tmp.xml"));
        const { publishDate, entities } = parseOfacXml(body, "OFAC-SDN");
        ofacSdnPublishDate = publishDate;
        console.log(`  curl: Parsed ${entities.length} entries`);
        for (const e of entities) {
          const uid = e.source_record_uid;
          if (!seenUids.has(uid)) { seenUids.add(uid); allEntities.push(e); }
        }
        sourceMeta["OFAC-SDN"] = {
          source_url: SOURCES["OFAC-SDN"].url,
          publish_date: publishDate,
          record_count: entities.length,
          retrieved_at: new Date().toISOString(),
          status: "OK",
        };
      } else {
        throw new Error(`curl exited ${result.status}`);
      }
    } catch (curlErr) {
      console.error(`  OFAC-SDN curl fallback also failed: ${curlErr.message}`);
      sourceMeta["OFAC-SDN"] = { status: "FAILED", reason: `${err.message}; curl: ${curlErr.message}` };
    }
  }

  // === OFAC CONS ===
  console.log("\nFetching OFAC Consolidated (non-SDN)...");
  try {
    const { body } = await fetchUrl(SOURCES["OFAC-CONS"].url);
    console.log(`  Downloaded ${Math.round(body.length / 1024)}KB`);
    const { publishDate, entities } = parseOfacXml(body, "OFAC-CONS");
    console.log(`  Parsed ${entities.length} entries (publish date: ${publishDate})`);
    let added = 0;
    for (const e of entities) {
      const uid = e.source_record_uid;
      if (!seenUids.has(uid)) {
        seenUids.add(uid);
        allEntities.push(e);
        added++;
      }
    }
    console.log(`  Added ${added} new OFAC-CONS entities (cross-source dedup by uid)`);
    sourceMeta["OFAC-CONS"] = {
      source_url: SOURCES["OFAC-CONS"].url,
      publish_date: publishDate,
      record_count: entities.length,
      retrieved_at: new Date().toISOString(),
      status: "OK",
    };
  } catch (err) {
    console.log(`  OFAC-CONS failed: ${err.message}`);
    sourceMeta["OFAC-CONS"] = { status: "PENDING", reason: err.message };
  }

  // === EU FSF ===
  console.log("\nProbing EU FSF...");
  const euResult = await probeSource("EU-FSF", SOURCES["EU-FSF"]);
  if (euResult.status === "OK" && euResult.body) {
    // Basic EU XML parsing (simplified — EU uses different schema)
    try {
      const body = euResult.body;
      const euEntries = [];
      // EU schema is complex; extract what we can
      const subjectRe = /<sanctionEntity[^>]*>([\s\S]*?)<\/sanctionEntity>/gi;
      let subjectMatch;
      while ((subjectMatch = subjectRe.exec(body)) !== null) {
        const sub = subjectMatch[1];
        const nameRe = /<nameAlias[^>]+wholeName="([^"]+)"/gi;
        let nm;
        const names = [];
        while ((nm = nameRe.exec(sub)) !== null) names.push(decodeXmlEntities(nm[1]));
        if (names.length === 0) continue;
        euEntries.push({
          name: names[0],
          aliases: names.slice(1),
          program: "EU-FSF",
          source: "EU-FSF",
          source_url: SOURCES["EU-FSF"].url,
          source_publish_date: "unknown",
          source_record_uid: `EU-FSF-${euEntries.length}`,
          retrieved_at: new Date().toISOString(),
        });
      }
      let added = 0;
      for (const e of euEntries) {
        const key = `EU-FSF-${e.name.toLowerCase()}`;
        if (!seenUids.has(key)) { seenUids.add(key); allEntities.push(e); added++; }
      }
      console.log(`  EU-FSF: Added ${added} entities`);
      sourceMeta["EU-FSF"] = {
        source_url: SOURCES["EU-FSF"].url,
        record_count: euEntries.length,
        retrieved_at: new Date().toISOString(),
        status: "OK",
      };
    } catch (euErr) {
      console.log(`  EU-FSF parse error: ${euErr.message}`);
      sourceMeta["EU-FSF"] = { status: "PENDING", reason: `parse-error: ${euErr.message}` };
    }
  } else {
    sourceMeta["EU-FSF"] = { status: "PENDING", reason: euResult.reason || "unreachable" };
  }

  // === UK OFSI ===
  console.log("Probing UK OFSI...");
  const ukResult = await probeSource("UK-OFSI", SOURCES["UK-OFSI"]);
  sourceMeta["UK-OFSI"] = ukResult.status === "OK"
    ? { source_url: SOURCES["UK-OFSI"].url, retrieved_at: new Date().toISOString(), status: "OK-CSV-PENDING-PARSE" }
    : { status: "PENDING", reason: ukResult.reason || "unreachable" };

  // === UN SC ===
  console.log("Probing UN SC...");
  const unResult = await probeSource("UN-SC", SOURCES["UN-SC"]);
  let unPublishDate = "not-published-by-source";
  if (unResult.status === "OK" && unResult.body) {
    try {
      const body = unResult.body;
      const unEntries = [];
      const individualRe = /<INDIVIDUAL>([\s\S]*?)<\/INDIVIDUAL>/gi;
      const entityRe = /<ENTITY>([\s\S]*?)<\/ENTITY>/gi;

      // Try to extract UN-SC publish date from root element dateGenerated or generation date attribute
      const dateGeneratedMatch = body.match(/dateGenerated["\s]*=\s*["\']([^\'"]+)["\']/i);
      if (dateGeneratedMatch) {
        unPublishDate = dateGeneratedMatch[1];
      } else {
        const pubDateMatch = body.match(/<(?:Publish_Date|GenerationDate|dateGenerated)>([\s\S]*?)<\/(?:Publish_Date|GenerationDate|dateGenerated)>/i);
        if (pubDateMatch) {
          unPublishDate = pubDateMatch[1].trim();
        }
      }

      function extractUnNames(block) {
        const fnMatch = block.match(/<FIRST_NAME>([\s\S]*?)<\/FIRST_NAME>/i);
        const snMatch = block.match(/<SECOND_NAME>([\s\S]*?)<\/SECOND_NAME>/i);
        const thirdMatch = block.match(/<THIRD_NAME>([\s\S]*?)<\/THIRD_NAME>/i);
        const parts = [fnMatch, snMatch, thirdMatch].filter(Boolean).map(m => decodeXmlEntities(m[1].trim())).filter(Boolean);
        return parts.length > 0 ? parts.join(" ") : null;
      }

      let block;
      while ((block = individualRe.exec(body)) !== null) {
        const name = extractUnNames(block[1]);
        if (!name || name.length < 3) continue;
        unEntries.push({ name, aliases: [], program: "UN-SC", source: "UN-SC", source_url: SOURCES["UN-SC"].url, source_publish_date: unPublishDate, source_record_uid: `UN-SC-${unEntries.length}`, retrieved_at: new Date().toISOString() });
      }
      while ((block = entityRe.exec(body)) !== null) {
        const enameMatch = block[1].match(/<FIRST_NAME>([\s\S]*?)<\/FIRST_NAME>/i);
        if (!enameMatch) continue;
        const name = decodeXmlEntities(enameMatch[1].trim());
        if (!name || name.length < 2) continue;
        unEntries.push({ name, aliases: [], program: "UN-SC", source: "UN-SC", source_url: SOURCES["UN-SC"].url, source_publish_date: unPublishDate, source_record_uid: `UN-SC-${unEntries.length}`, retrieved_at: new Date().toISOString() });
      }

      let added = 0;
      for (const e of unEntries) {
        const key = `UN-SC-${e.name.toLowerCase()}`;
        if (!seenUids.has(key)) { seenUids.add(key); allEntities.push(e); added++; }
      }
      console.log(`  UN-SC: Added ${added} entities (publish date: ${unPublishDate})`);
      sourceMeta["UN-SC"] = { source_url: SOURCES["UN-SC"].url, record_count: unEntries.length, publish_date: unPublishDate, retrieved_at: new Date().toISOString(), status: "OK" };
    } catch (unErr) {
      console.log(`  UN-SC parse error: ${unErr.message}`);
      sourceMeta["UN-SC"] = { status: "PENDING", reason: `parse-error: ${unErr.message}` };
    }
  } else {
    sourceMeta["UN-SC"] = { status: "PENDING", reason: unResult.reason || "unreachable" };
  }

  // === Build output ===
  console.log(`\nTotal entities before dedup: ${allEntities.length}`);

  // Name-based dedup across sources (case-insensitive)
  const seenNames = new Map();
  const dedupedEntities = [];
  for (const e of allEntities) {
    const key = e.name.toLowerCase().replace(/\s+/g, " ").trim();
    if (!seenNames.has(key)) {
      seenNames.set(key, true);
      dedupedEntities.push(e);
    }
  }
  console.log(`Total entities after dedup: ${dedupedEntities.length}`);

  const output = {
    _meta: {
      status: "AUTHORITATIVE-INGESTED",
      sources: sourceMeta,
      total_entities: dedupedEntities.length,
      generated_at: new Date().toISOString(),
      refresh_cadence: {
        OFAC: "daily T+1 delta",
        EU: "weekly Monday UTC",
        UK: "weekly Monday UTC",
        UN: "weekly Monday UTC",
      },
      staleness_guard: "OFAC publish_date>2 business days old OR others>8 days → STALE (uses source publish_date when available, falls back to retrieved_at)",
      ingest_command: "node scripts/ingest-sanctions.mjs",
    },
    entities: dedupedEntities,
  };

  console.log(`\nWriting ${OUT_PATH}...`);
  fs.writeFileSync(OUT_PATH, JSON.stringify(output, null, 2), "utf8");
  console.log(`  Written ${Math.round(fs.statSync(OUT_PATH).size / 1024)}KB`);

  // === Write sample (10 real OFAC-sourced entities) ===
  const ofacEntities = dedupedEntities.filter(e => e.source === "OFAC-SDN").slice(0, 10);
  const sample = {
    _meta: {
      status: "AUTHORITATIVE-SAMPLE",
      description: "10 real OFAC-SDN sourced entities — offline fallback + test fixture",
      source: "OFAC-SDN",
      source_url: SOURCES["OFAC-SDN"].url,
      generated_at: new Date().toISOString(),
    },
    entities: ofacEntities,
  };
  fs.writeFileSync(SAMPLE_PATH, JSON.stringify(sample, null, 2), "utf8");
  console.log(`Wrote sample: ${SAMPLE_PATH} (${ofacEntities.length} entities)`);

  // Summary
  console.log("\n=== SUMMARY ===");
  console.log(`OFAC publish date: ${ofacSdnPublishDate}`);
  console.log(`Total entities: ${dedupedEntities.length}`);
  for (const [key, meta] of Object.entries(sourceMeta)) {
    console.log(`  ${key}: ${meta.status}${meta.record_count ? ` (${meta.record_count} records)` : ""}${meta.reason ? ` — ${meta.reason}` : ""}`);
  }
  console.log(`\nDone. ${new Date().toISOString()}`);
}

main().catch(err => {
  console.error("FATAL:", err);
  process.exit(1);
});
