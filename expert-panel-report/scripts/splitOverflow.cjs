/**
 * splitOverflow.cjs
 * 可复用工具：在 Playwright page.pdf() 之前自动修复 .page 溢出
 *
 * 用法：
 *   const { fixOverflow } = require('./scripts/splitOverflow.cjs');
 *   await fixOverflow(playwrightPage);
 *   await playwrightPage.pdf({ ... });
 *
 * 原理：
 *   1. 遍历所有 .page，临时清除 min-height 后测量真实内容高度
 *   2. 若超过 A4（297mm），从末尾向前二分找分割点（最后一个让内容<=A4的直接子元素）
 *   3. 将分割点之后的元素移入新建 .page，恢复 min-height
 *   4. 重复直至收敛，最后统一更新页码
 *
 * 关键技巧：
 *   - 检测时临时 minHeight='0' 排除 min-height 干扰；分割后恢复
 *   - 对 .content-page 布局页，分割在 .main-col 内完成，侧栏克隆保留
 *   - 对全宽页（摘要/目录），分割在唯一子容器 div 内完成
 */
'use strict';

const A4_MM   = 297;
const A4_PX   = (A4_MM / 25.4) * 96; // ≈ 1122.52px @96dpi

/**
 * @param {import('playwright').Page} page  已 goto 的 Playwright page
 * @param {object} [opts]
 * @param {number} [opts.a4px]         A4 高度（px）
 * @param {number} [opts.maxPasses=20] 防死循环
 */
async function fixOverflow(page, opts = {}) {
  const { a4px = A4_PX, maxPasses = 20 } = opts;

  for (let pass = 0; pass < maxPasses; pass++) {
    const splitHappened = await page.evaluate((A4) => {
      /**
       * 测量元素的真实内容高度（排除 min-height 干扰）
       */
      function trueHeight(el) {
        const prevMin = el.style.minHeight;
        const prevH   = el.style.height;
        el.style.minHeight = '0';
        el.style.height = 'auto';
        const h = el.getBoundingClientRect().height;
        el.style.minHeight = prevMin;
        el.style.height = prevH;
        return h;
      }

      const pages = Array.from(document.querySelectorAll('.page'));

      for (const pg of pages) {
        if (trueHeight(pg) <= A4) continue;          // 无溢出，跳过

        // ── 定位容器和子元素 ──────────────────────────
        const isContentPage = !!pg.querySelector('.content-page');
        let container;
        if (isContentPage) {
          container = pg.querySelector('.main-col');
        } else if (pg.children.length === 1) {
          container = pg.children[0];                // 全宽包裹 div
        } else {
          container = pg;
        }
        if (!container) continue;

        const children = Array.from(container.children).filter(
          c => getComputedStyle(c).position !== 'absolute'  // 排除绝对定位（如页码）
        );
        if (children.length <= 1) continue;          // 无法再拆

        // ── 二分查找分割点 ─────────────────────────────
        // 从末尾逐一隐藏，找到第一个让 pg 真实高度 ≤ A4 的 i
        let splitIdx = -1;
        for (let i = children.length - 1; i >= 1; i--) {
          // 临时隐藏 [i .. end]
          for (let j = i; j < children.length; j++) children[j].style.display = 'none';
          const h = trueHeight(pg);
          for (let j = i; j < children.length; j++) children[j].style.display = '';
          if (h <= A4) { splitIdx = i; break; }
        }
        if (splitIdx < 1) continue;                  // 单元素超页，无法自动拆

        // ── 构建新 .page ──────────────────────────────
        const newPage = document.createElement('div');
        newPage.className = pg.className;

        if (isContentPage) {
          const oldCP    = pg.querySelector('.content-page');
          const newCP    = document.createElement('div');
          newCP.className = 'content-page';

          // 克隆侧栏（页码由后续统一更新）
          newCP.appendChild(oldCP.querySelector('.sidebar-col').cloneNode(true));

          // 新 main-col 装溢出内容
          const newMain    = document.createElement('div');
          newMain.className = 'main-col';
          children.slice(splitIdx).forEach(el => newMain.appendChild(el));
          newCP.appendChild(newMain);
          newPage.appendChild(newCP);
        } else {
          // 全宽页：克隆外壳，移入溢出内容
          const newContainer = container.cloneNode(false);
          children.slice(splitIdx).forEach(el => newContainer.appendChild(el));
          newPage.appendChild(newContainer);
        }

        pg.parentNode.insertBefore(newPage, pg.nextSibling);
        return true;    // 每轮只处理一次溢出，重新扫描
      }
      return false;     // 无溢出，收敛
    }, a4px);

    if (!splitHappened) break;
  }

  // ── 统一更新页码 ───────────────────────────────────
  await page.evaluate(() => {
    const pages = Array.from(document.querySelectorAll('.page'));
    const total = pages.length;
    pages.forEach((pg, idx) => {
      const n = idx + 1;
      // 侧栏 .sb-pagenum
      pg.querySelectorAll('.sb-pagenum').forEach(el => {
        el.textContent = `Page ${n} / ${total}`;
      });
      // 全宽底部居中页码（position:absolute + bottom:14mm）
      pg.querySelectorAll('[style*="position:absolute"]').forEach(el => {
        if (/Page\s+\d+/.test(el.textContent)) {
          el.textContent = `Page ${n} / ${total}`;
        }
      });
    });
  });
}

module.exports = { fixOverflow };
