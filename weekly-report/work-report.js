#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');

class WorkReportGenerator {
  constructor(options = {}) {
    this.template = options.template || 'standard';
    this.mcReportDir = process.env.MC_REPORT_DIR || path.join(os.homedir(), 'Desktop', 'MC周报');
    this.output = options.output || this.getDefaultOutputPath();
    this.interactive = options.interactive || false;
    this.data = {};
  }

  getDefaultOutputPath() {
    const date = new Date().toISOString().split('T')[0];
    return `${this.mcReportDir}/工作周报_${date}.md`;
  }

  async generateInteractiveReport() {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    console.log('📝 交互式周报生成器\n');

    // 收集基本信息
    this.data.author = await this.question(rl, '👤 您的姓名: ');
    this.data.department = await this.question(rl, '🏢 部门: ');
    this.data.week = await this.question(rl, '📅 第几周 (留空自动计算): ') || this.getWeekNumber();
    
    console.log('\n📊 本周工作内容 (输入空行结束):');
    this.data.workItems = await this.collectMultilineInput(rl, '工作项目');
    
    console.log('\n📈 本周成果/数据 (输入空行结束):');
    this.data.achievements = await this.collectMultilineInput(rl, '成果数据');
    
    console.log('\n🎯 下周计划 (输入空行结束):');
    this.data.nextWeekPlan = await this.collectMultilineInput(rl, '计划项目');
    
    console.log('\n⚠️ 遇到的问题 (输入空行结束，可选):');
    this.data.issues = await this.collectMultilineInput(rl, '问题描述');
    
    console.log('\n💭 其他思考 (输入空行结束，可选):');
    this.data.thoughts = await this.collectMultilineInput(rl, '思考内容');

    rl.close();
    
    const report = this.formatReport();
    
    if (this.output) {
      // 确保MC周报目录存在
      if (!fs.existsSync(this.mcReportDir)) {
        fs.mkdirSync(this.mcReportDir, { recursive: true });
      }
      fs.writeFileSync(this.output, report);
      console.log(`\n✅ 周报已保存到: ${this.output}`);
    } else {
      console.log('\n' + '='.repeat(60));
      console.log(report);
    }

    return report;
  }

  async question(rl, prompt) {
    return new Promise(resolve => {
      rl.question(prompt, answer => resolve(answer.trim()));
    });
  }

  async collectMultilineInput(rl, itemName) {
    const items = [];
    let lineNumber = 1;
    
    while (true) {
      const line = await this.question(rl, `  ${lineNumber}. `);
      if (line === '') break;
      items.push(line);
      lineNumber++;
    }
    
    return items;
  }

  generateFromTemplate(data = {}) {
    this.data = { ...this.getDefaultData(), ...data };
    return this.formatReport();
  }

  getDefaultData() {
    return {
      author: '张三',
      department: '技术部',
      week: this.getWeekNumber(),
      workItems: [
        '完成项目A的核心功能开发',
        '修复系统中的关键bug',
        '参与代码审核和技术讨论'
      ],
      achievements: [
        '代码提交: 15次',
        '解决问题: 5个',
        '文档更新: 3篇'
      ],
      nextWeekPlan: [
        '开始项目B的需求分析',
        '完善项目A的测试用例',
        '准备技术分享材料'
      ],
      issues: [
        '第三方API响应较慢，影响开发进度',
        '需要更多时间学习新技术栈'
      ],
      thoughts: [
        '本周工作效率较高，按时完成了既定目标',
        '发现了一些可以优化的开发流程'
      ]
    };
  }

  formatReport() {
    const startDate = this.getWeekStartDate();
    const endDate = this.getWeekEndDate();

    let report = `# 工作周报 - 第${this.data.week}周\n\n`;
    report += `**姓名**: ${this.data.author}\n`;
    report += `**部门**: ${this.data.department}\n`;
    report += `**报告期间**: ${startDate} 至 ${endDate}\n`;
    report += `**生成时间**: ${new Date().toLocaleString('zh-CN')}\n\n`;

    // 本周工作总结
    report += `## 📊 本周工作总结\n\n`;
    this.data.workItems.forEach((item, index) => {
      report += `${index + 1}. ${item}\n`;
    });
    report += '\n';

    // 本周成果/数据
    if (this.data.achievements && this.data.achievements.length > 0) {
      report += `## 📈 本周成果与数据\n\n`;
      this.data.achievements.forEach(achievement => {
        report += `- ${achievement}\n`;
      });
      report += '\n';
    }

    // 下周计划
    report += `## 🎯 下周工作计划\n\n`;
    this.data.nextWeekPlan.forEach((plan, index) => {
      report += `${index + 1}. ${plan}\n`;
    });
    report += '\n';

    // 遇到的问题
    if (this.data.issues && this.data.issues.length > 0) {
      report += `## ⚠️ 遇到的问题\n\n`;
      this.data.issues.forEach(issue => {
        report += `- ${issue}\n`;
      });
      report += '\n';
    }

    // 其他思考
    if (this.data.thoughts && this.data.thoughts.length > 0) {
      report += `## 💭 其他思考\n\n`;
      this.data.thoughts.forEach(thought => {
        report += `- ${thought}\n`;
      });
      report += '\n';
    }

    report += `---\n`;
    report += `*此报告由智能周报生成器创建于 ${new Date().toLocaleString('zh-CN')}*\n`;

    return report;
  }

  getWeekNumber() {
    const now = new Date();
    const start = new Date(now.getFullYear(), 0, 1);
    const week = Math.ceil(((now - start) / 86400000 + start.getDay() + 1) / 7);
    return week;
  }

  getWeekStartDate() {
    const now = new Date();
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1); // 调整为周一
    const monday = new Date(now.setDate(diff));
    return monday.toISOString().split('T')[0];
  }

  getWeekEndDate() {
    const now = new Date();
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? 0 : 7); // 调整为周日
    const sunday = new Date(now.setDate(diff));
    return sunday.toISOString().split('T')[0];
  }
}

// 命令行接口
if (require.main === module) {
  const args = process.argv.slice(2);
  const options = {};

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--interactive':
      case '-i':
        options.interactive = true;
        break;
      case '--output':
      case '-o':
        options.output = args[++i];
        break;
      case '--template':
        options.template = args[++i];
        break;
      case '--demo':
        // 生成示例报告
        const demo = new WorkReportGenerator(options);
        const demoReport = demo.generateFromTemplate();
        console.log(demoReport);
        process.exit(0);
      case '--help':
        console.log(`
工作周报生成器

用法: node work-report.js [选项]

选项:
  --interactive, -i       交互式创建周报
  --output, -o <file>     输出文件路径
  --template <type>       模板类型 (standard|corporate)
  --demo                  生成示例周报
  --help                  显示帮助

示例:
  node work-report.js --interactive
  node work-report.js --demo
  node work-report.js --interactive --output weekly-report.md
        `);
        process.exit(0);
    }
  }

  const generator = new WorkReportGenerator(options);
  
  if (options.interactive) {
    generator.generateInteractiveReport()
      .catch(error => {
        console.error('生成周报失败:', error.message);
        process.exit(1);
      });
  } else {
    // 默认生成示例报告
    const report = generator.generateFromTemplate();
    if (options.output) {
      fs.writeFileSync(options.output, report);
      console.log(`周报已保存到: ${options.output}`);
    } else {
      console.log(report);
    }
  }
}

module.exports = { WorkReportGenerator };