// 将这段代码插入到 handleResetAllAssignments 函数中
// 在删除 session 记录之后，删除 progress 记录之前

// 🗄️ 备份并清理 R2 中的 results 文件
let r2ResultsCount = 0;
let r2ResultsBackedUp = 0;
if (env.ARC_BUCKET) {
  try {
    const resultsObjects = await env.ARC_BUCKET.list({ prefix: 'results/' });
    r2ResultsCount = resultsObjects.objects.length;
    
    // 备份：将 results/ 中的文件复制到 results_backup_{timestamp}/
    const backupPrefix = `results_backup_${resetTimestamp.replace(/[:.]/g, '')}`;
    
    for (const obj of resultsObjects.objects) {
      // 读取原文件
      const originalObject = await env.ARC_BUCKET.get(obj.key);
      if (originalObject) {
        // 生成备份路径：results/xxx.json → results_backup_20250117/xxx.json
        const backupKey = obj.key.replace('results/', `${backupPrefix}/`);
        
        // 保存到备份路径
        await env.ARC_BUCKET.put(backupKey, await originalObject.text());
        r2ResultsBackedUp++;
        
        // 删除原文件
        await env.ARC_BUCKET.delete(obj.key);
      }
    }
    
    console.log(`✓备份并清理了 ${r2ResultsBackedUp} 个 R2 results 文件到 ${backupPrefix}/`);
  } catch (error) {
    console.error('R2 results backup error:', error);
  }
}

// 然后在返回的 response 中添加：
// r2_results_backed_up: r2ResultsBackedUp,
// r2_results_backup_prefix: backupPrefix (如果有)
