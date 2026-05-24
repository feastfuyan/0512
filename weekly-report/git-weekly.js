#!/usr/bin/env node

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

class GitWeeklyReporter {
  constructor(options = {}) {
    this.repos = Array.isArray(options.repos) ? options.repos : [options.repo || process.cwd()];
    this.days = options.days || 7;
    this.author = options.author || null;
    this.since = options.since || this.calculateSince();
    this.aiOptimize = options.ai || false;
    this.format = options.format || 'markdown';
    this.mcReportDir = process.env.MC_REPORT_DIR || path.join(os.homedir(), 'Desktop', 'MC周报');
    this.outputPath = options.output || this.getDefaultOutputPath();
  }

  getDefaultOutputPath() {
    const date = new Date().toISOString().split('T')[0];
    return `${this.mcReportDir}/周报_${date}.md`;
  }

  calculateSince() {
    const date = new Date();
    date.setDate(date.getDate() - this.days);
    return date.toISOString().split('T')[0];
  }

  async generateReport() {
    console.log(`生成周报: ${this.since} 至今 (${this.days}天)`);
    
    const allCommits = [];
    const repoStats = [];

    for (const repo of this.repos) {
      if (!fs.existsSync(repo)) {
        console.warn(`仓库路径不存在: ${repo}`);
        continue;
      }

      console.log(`分析仓库: ${repo}`);
      const commits = this.getGitCommits(repo);
      const stats = this.getRepoStats(repo);
      
      allCommits.push(...commits.map(c => ({ ...c, repo: path.basename(repo) })));
      repoStats.push({ name: path.basename(repo), ...stats });
    }

    const groupedCommits = this.groupCommitsByRepo(allCommits);
    const report = await this.formatReport(groupedCommits, repoStats);

    if (this.outputPath) {
      // 确保MC周报目录存在
      if (!fs.existsSync(this.mcReportDir)) {
        fs.mkdirSync(this.mcReportDir, { recursive: true });
      }
      fs.writeFileSync(this.outputPath, report);
      console.log(`周报已保存到: ${this.outputPath}`);
    }

    return report;
  }

  getGitCommits(repoPath) {
    try {
      const authorFilter = this.author ? `--author="${this.author}"` : '';
      const cmd = `cd "${repoPath}" && git log --since="${this.since}" ${authorFilter} --pretty=format:"%H|%an|%ad|%s" --date=short`;
      
      const output = execSync(cmd, { encoding: 'utf8' }).trim();
      
      if (!output) return [];

      return output.split('\n').map(line => {
        const [hash, author, date, message] = line.split('|');
        return { hash, author, date, message };
      });
    } catch (error) {
      console.error(`获取Git提交失败: ${repoPath}`, error.message);
      return [];
    }
  }

  getRepoStats(repoPath) {
    try {
      const authorFilter = this.author ? `--author="${this.author}"` : '';
      
      // 提交次数
      const commitCountCmd = `cd "${repoPath}" && git log --since="${this.since}" ${authorFilter} --oneline | wc -l`;
      const commitCount = parseInt(execSync(commitCountCmd, { encoding: 'utf8' }).trim()) || 0;

      // 代码行数变化
      const statsCmd = `cd "${repoPath}" && git log --since="${this.since}" ${authorFilter} --numstat --pretty=format:""`;
      const statsOutput = execSync(statsCmd, { encoding: 'utf8' }).trim();
      
      let addedLines = 0;
      let deletedLines = 0;
      let filesChanged = 0;

      if (statsOutput) {
        const lines = statsOutput.split('\n').filter(line => line.trim());
        lines.forEach(line => {
          const [added, deleted] = line.split('\t');
          if (added && added !== '-' && deleted && deleted !== '-') {
            addedLines += parseInt(added) || 0;
            deletedLines += parseInt(deleted) || 0;
            filesChanged++;
          }
        });
      }

      return {
        commitCount,
        addedLines,
        deletedLines,
        filesChanged,
        netLines: addedLines - deletedLines
      };
    } catch (error) {
      console.error(`获取仓库统计失败: ${repoPath}`, error.message);
      return { commitCount: 0, addedLines: 0, deletedLines: 0, filesChanged: 0, netLines: 0 };
    }
  }

  groupCommitsByRepo(commits) {
    const grouped = {};
    commits.forEach(commit => {
      if (!grouped[commit.repo]) {
        grouped[commit.repo] = [];
      }
      grouped[commit.repo].push(commit);
    });
    return grouped;
  }

  async formatReport(groupedCommits, repoStats) {
    const startDate = this.since;
    const endDate = new Date().toISOString().split('T')[0];
    const weekNumber = this.getWeekNumber();

    let report = `# 工作周报 - 第${weekNumber}周\n\n`;
    report += `**报告期间**: ${startDate} 至 ${endDate}\n`;
    report += `**生成时间**: ${new Date().toLocaleString('zh-CN')}\n\n`;
    report += `---\n\n`;

    // ========== 项目维度汇报 ==========
    const activeProjects = Object.entries(groupedCommits).filter(([repo, commits]) => commits.length > 0);
    
    for (let i = 0; i < activeProjects.length; i++) {
      const [repo, commits] = activeProjects[i];
      const repoStat = repoStats.find(s => s.name === repo) || {};
      
      report += `## 📦 项目 ${i + 1}：${repo}\n\n`;
      
      // 项目工作内容
      report += `### 📊 本周工作\n\n`;
      const categories = this.categorizeCommits(commits);
      
      for (const [category, categoryCommits] of Object.entries(categories)) {
        if (categoryCommits.length === 0) continue;
        
        report += `**${category}** (${categoryCommits.length}项):\n`;
        categoryCommits.forEach(commit => {
          report += `- ${commit.message}\n`;
        });
        report += '\n';
      }
      
      // 项目数据统计
      report += `### 📈 项目数据\n\n`;
      report += `- 提交次数: ${repoStat.commitCount || 0}\n`;
      report += `- 代码变更: +${repoStat.addedLines || 0}/-${repoStat.deletedLines || 0} 行\n`;
      if (repoStat.filesChanged > 0) {
        report += `- 涉及文件: ${repoStat.filesChanged} 个\n`;
      }
      report += '\n';
      
      // 项目下周计划
      report += `### 🎯 下周计划\n\n`;
      const suggestedPlans = this.suggestNextWeekPlans(categories, commits);
      suggestedPlans.forEach(plan => {
        report += `- ${plan}\n`;
      });
      report += '\n';
      
      // 项目问题
      const issues = this.identifyIssues(commits);
      if (issues.length > 0) {
        report += `### ⚠️ 遇到的问题\n\n`;
        issues.forEach(issue => {
          report += `- ${issue}\n`;
        });
        report += '\n';
      }
      
      report += `---\n\n`;
    }

    // ========== 总体汇总 ==========
    const totalStats = repoStats.reduce((total, stat) => ({
      commitCount: total.commitCount + stat.commitCount,
      addedLines: total.addedLines + stat.addedLines,
      deletedLines: total.deletedLines + stat.deletedLines,
      filesChanged: total.filesChanged + stat.filesChanged,
      netLines: total.netLines + stat.netLines
    }), { commitCount: 0, addedLines: 0, deletedLines: 0, filesChanged: 0, netLines: 0 });

    report += `## 📊 总体汇总\n\n`;
    report += `**涉及项目**: ${activeProjects.length} 个\n\n`;
    report += `### 总体数据\n\n`;
    report += `- 总提交次数: ${totalStats.commitCount}\n`;
    report += `- 代码变更: +${totalStats.addedLines}/-${totalStats.deletedLines} 行\n`;
    report += `- 净增加代码: ${totalStats.netLines} 行\n`;
    report += `- 涉及文件: ${totalStats.filesChanged} 个\n\n`;
    
    if (totalStats.commitCount > 0) {
      const avgCommitsPerDay = (totalStats.commitCount / this.days).toFixed(1);
      report += `> 💡 本周平均每天 ${avgCommitsPerDay} 次提交\n\n`;
    }

    report += `---\n`;
    report += `*此报告由智能周报生成器自动生成*\n`;

    return report;
  }

  // 根据本周工作建议下周计划
  suggestNextWeekPlans(categories, commits) {
    const plans = [];
    
    if (categories['功能开发'].length > 0) {
      plans.push('继续推进功能开发，确保按时交付');
      plans.push('完成相关功能的测试验证');
    }
    
    if (categories['问题修复'].length > 0) {
      plans.push('持续监控系统稳定性');
      plans.push('完善异常处理机制');
    }
    
    if (categories['代码优化'].length > 0) {
      plans.push('持续优化代码质量和性能');
    }
    
    if (categories['文档更新'].length === 0) {
      plans.push('补充技术文档');
    }
    
    if (plans.length === 0) {
      plans.push('推进项目开发进度');
    }
    
    return plans.slice(0, 4); // 最多返回4条
  }

  // 从提交记录识别潜在问题
  identifyIssues(commits) {
    const issues = [];
    
    commits.forEach(commit => {
      const msg = commit.message.toLowerCase();
      
      // 检测性能相关
      if (msg.includes('performance') || msg.includes('慢') || msg.includes('性能')) {
        issues.push('存在性能优化需求，需持续关注');
      }
      
      // 检测安全相关
      if (msg.includes('security') || msg.includes('安全') || msg.includes('漏洞')) {
        issues.push('存在安全隐患，需加强安全防护');
      }
      
      // 检测紧急修复
      if (msg.includes('hotfix') || msg.includes('紧急') || msg.includes('critical')) {
        issues.push('出现紧急问题，需关注根因分析');
      }
    });
    
    // 去重
    return [...new Set(issues)];
  }

  categorizeCommits(commits) {
    const categories = {
      '功能开发': [],
      '问题修复': [],
      '代码优化': [],
      '文档更新': [],
      '其他': []
    };

    commits.forEach(commit => {
      const message = commit.message.toLowerCase();
      
      if (message.includes('fix') || message.includes('修复') || message.includes('bug')) {
        categories['问题修复'].push(commit);
      } else if (message.includes('feat') || message.includes('add') || message.includes('新增') || message.includes('功能')) {
        categories['功能开发'].push(commit);
      } else if (message.includes('refactor') || message.includes('optimize') || message.includes('优化') || message.includes('重构')) {
        categories['代码优化'].push(commit);
      } else if (message.includes('doc') || message.includes('readme') || message.includes('文档')) {
        categories['文档更新'].push(commit);
      } else {
        categories['其他'].push(commit);
      }
    });

    return categories;
  }

  getWeekNumber() {
    const now = new Date();
    const start = new Date(now.getFullYear(), 0, 1);
    const week = Math.ceil(((now - start) / 86400000 + start.getDay() + 1) / 7);
    return week;
  }
}

// 命令行接口
if (require.main === module) {
  const args = process.argv.slice(2);
  const options = {};

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--repo':
        options.repo = args[++i];
        break;
      case '--repos':
        options.repos = args[++i].split(',').map(r => r.trim());
        break;
      case '--days':
        options.days = parseInt(args[++i]);
        break;
      case '--author':
        options.author = args[++i];
        break;
      case '--since':
        options.since = args[++i];
        break;
      case '--output':
      case '-o':
        options.output = args[++i];
        break;
      case '--ai':
        options.ai = true;
        break;
      case '--format':
        options.format = args[++i];
        break;
      case '--help':
        console.log(`
Git周报生成器

用法: node git-weekly.js [选项]

选项:
  --repo <path>           单个仓库路径 (默认: 当前目录)
  --repos <paths>         多个仓库路径，逗号分隔
  --days <number>         报告天数 (默认: 7)
  --author <name>         指定作者 (默认: 所有作者)
  --since <date>          开始日期 YYYY-MM-DD
  --output, -o <file>     输出文件路径
  --ai                    启用AI优化
  --format <type>         输出格式 (markdown|html|pdf)
  --help                  显示帮助

示例:
  node git-weekly.js --repo ./project --days 7
  node git-weekly.js --repos "./proj1,./proj2" --author "张三"
  node git-weekly.js --repo ./project --output weekly-report.md
        `);
        process.exit(0);
    }
  }

  const reporter = new GitWeeklyReporter(options);
  
  reporter.generateReport()
    .then(report => {
      if (!options.output) {
        console.log('\n' + report);
      }
    })
    .catch(error => {
      console.error('生成周报失败:', error.message);
      process.exit(1);
    });
}

module.exports = { GitWeeklyReporter };