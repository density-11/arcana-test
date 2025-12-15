// Cloudflare Worker for ARCANA Test Platform API
// Version: 2.5.15
// Last Updated: 2025-10-21
// Deploy Verification ID: DEPLOY_20251021_v2.5.15_RACE_CONDITION_FIX
//
// 将此文件部署到Cloudflare Worker 来处理API 请求
//
// 🔧 v2.5.15 竞态条件修复 (2025-10-21):
// - 添加 pending 锁状态（分配进行中时防止重复请求）
// - 改进错误日志和类型分类（parse_error, timeout_error 等）
// - 前端自动重试机制（assignment_in_progress 时 2 秒后重试）
// - 详细的 JSON 解析错误处理和原始响应日志
//
// 🕐 超时功能 (v1.1 + v2.5.6 + v2.5.8 + v2.5.14):
// - 120小时超时限制：URL分配后120小时（5天）内未完成将自动标记为 timeout_locked (v2.5.14 更新，适用于20道题)
// - 被动检查：在获取分配和提交结果时自动检查超时状态
// - 主动清理：Cron Job 每 6 小时扫描并回收超时分配 (v2.5.6)
// - 完整回收：更新 session_ 状态、删除 used_ 键、归档 progress_ 数据
// - 保留记录：session_ 键不删除，仅更新 status='timeout_locked' (v2.5.8，便于审计)
// - 拒绝提交：超时后的提交将被拒绝，返回 403 错误
// - 前端提示：前端会显示超时锁定屏幕，包含多语言支持
//
// 🔒 v2.5.1 关键修复 (2025-10-17):
// - handleAttentionCheckFailed: 提前保存 assignment 防止并发问题
// - handleSubmitResults: 双重检查 locked 和 attention_check_failed 状态
// - 添加详细日志用于调试状态检查
//
// 🆕 v2.5.6 新功能 (2025-10-20):
// - Cron Trigger: 每 6 小时自动扫描并清理超时分配
// - cleanupTimeoutAssignments(): 主动清理函数
// - 清理日志记录到 KV (cleanup_log_*, cleanup_error_*)
// - 与被动检查使用相同的回收逻辑，确保一致性
//
// 🔧 v2.5.7 修复 (2025-10-20):
// - handleAdminDownload: 修复 "result not found" 错误
// - 正确从 assignment.result_id 读取结果ID
// - 优先从 ARC_RESULTS KV 获取，回退到 R2 Bucket
// - 添加详细的调试日志
//
// 🔧 v2.5.8 优化 (2025-10-20):
// - 超时回收不再删除 session_ 键，改为更新状态
// - session.status = 'timeout_locked' 便于历史审计和追踪
// - index.html 需要过滤 status='timeout_locked' 的 session

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // CORS headers - 允许跨域访问
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    // 处理 CORS 预检请求
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      console.log(`[Worker] Processing ${request.method} ${url.pathname}${url.search}`);

      // 🔧 特殊处理: /app 返回 test.html 内容
      // 使用 /app 路径避开 Pages 对 /test 和 /test.html 的特殊处理
      if (url.pathname === '/app') {
        console.log(`[/app] Serving test.html content with query: ${url.search}`);
        // 创建一个新请求，指向 test.html 静态文件
        const assetUrl = new URL(request.url);
        assetUrl.pathname = '/test.html';
        const assetRequest = new Request(assetUrl.toString(), request);
        const assetResponse = await env.ASSETS.fetch(assetRequest);
        console.log(`[/app] Asset response status: ${assetResponse.status}`);
        return assetResponse;
      }

      // API 路由处理
      switch (url.pathname) {
        case '/api/upload':
          if (request.method === 'POST') {
            return await handleUpload(request, corsHeaders);
          }
          break;

        case '/api/get_problems':
          if (request.method === 'GET') {
            return await handleGetProblems(request, corsHeaders, env);
          }
          break;

        case '/api/get_tutorials':
          if (request.method === 'GET') {
            return await handleGetTutorials(request, corsHeaders, env);
          }
          break;

        case '/api/submit_results':
          if (request.method === 'POST') {
            return await handleSubmitResults(request, corsHeaders, env);
          }
          break;

        case '/api/list_json_files':
          if (request.method === 'GET') {
            return await handleListJsonFiles(request, corsHeaders, env);
          }
          break;

        case '/api/test_groups':
          if (request.method === 'GET') {
            return await handleTestGroups(corsHeaders, env);
          }
          break;

        case '/api/load_remote_json':
          if (request.method === 'POST') {
            return await handleLoadRemoteJson(request, corsHeaders, env);
          }
          break;

        case '/api/get_assignment':
          if (request.method === 'GET') {
            return await handleGetAssignment(request, corsHeaders, env);
          }
          break;

        case '/api/update_participant_id':
          if (request.method === 'POST') {
            return await handleUpdateParticipantId(request, corsHeaders, env);
          }
          break;

        case '/api/verify_participant_id':
          if (request.method === 'POST') {
            return await handleVerifyParticipantId(request, corsHeaders, env);
          }
          break;

        case '/api/assign_url':
          if (request.method === 'POST') {
            return await handleAssignUrl(request, corsHeaders, env);
          }
          break;

        case '/api/stats':
          if (request.method === 'GET') {
            return await handleGetStats(request, corsHeaders, env);
          }
          break;

        case '/api/attention_check_failed':
        case '/attention_check_failed':
          if (request.method === 'POST') {
            return await handleAttentionCheckFailed(request, corsHeaders, env);
          }
          break;

        // 进度保存与加载(v2.4.0)
        case '/api/save_progress':
        case '/save_progress':
          if (request.method === 'POST') {
            return await handleSaveProgress(request, corsHeaders, env);
          }
          break;

        case '/api/load_progress':
        case '/load_progress':
          if (request.method === 'GET' || request.method === 'POST') {
            return await handleLoadProgress(request, corsHeaders, env);
          }
          break;

        case '/api/check_saved_progress':
        case '/check_saved_progress':
          if (request.method === 'GET' || request.method === 'POST') {
            return await handleCheckSavedProgress(request, corsHeaders, env);
          }
          break;

        // 处理再分配请求
        case '/api/reassign_url':
          if (request.method === 'POST') {
            return await handleReassignUrl(request, corsHeaders, env);
          }
          break;

        // 处理重置所有分配请求
        case '/api/reset_all_assignments':
        case '/reset_all_assignments':
          if (request.method === 'POST') {
            return await handleResetAllAssignments(request, corsHeaders, env);
          }
          break;

        // 🆕 查询被试答案（公开访问，用于 /answers 页面）
        case '/api/query_answers':
          if (request.method === 'GET') {
            return await handleQueryAnswers(request, corsHeaders, env);
          }
          break;

        // Admin API 端点 (需要认证)
        case '/api/admin/stats':
          if (request.method === 'GET') {
            // 检查Basic Auth
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminStats(request, corsHeaders, env);
          }
          break;

        case '/api/admin/assignments':
          if (request.method === 'GET') {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminAssignments(request, corsHeaders, env);
          }
          break;

        case '/api/admin/export':
          if (request.method === 'POST') {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminExport(request, corsHeaders, env);
          }
          break;

        case '/api/admin/cleanup':
          if (request.method === 'POST') {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminCleanup(request, corsHeaders, env);
          }
          break;

        case '/api/admin/cleanup_duplicates':
          if (request.method === 'POST') {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminCleanupDuplicates(request, corsHeaders, env);
          }
          break;

        case '/api/admin/fix_available_groups':
          if (request.method === 'POST') {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            return await handleAdminFixAvailableGroups(request, corsHeaders, env);
          }
          break;

        // 🆕 v2.5.16: 测试组诊断端点（公开访问，用于快速诊断）
        case '/api/debug/test_groups_status':
        case '/debug/test_groups_status':
          if (request.method === 'GET') {
            return await handleDebugTestGroupsStatus(request, corsHeaders, env);
          }
          break;

        case '/start':
          if (request.method === 'GET') {
            return await handleAutoAssignStart(request, corsHeaders, env);
          }
          break;

        case '/api/version':
          // 版本检查端点- 用于验证部署
          return new Response(JSON.stringify({
            version: '2.5.15',
            deployId: 'DEPLOY_20251021_v2.5.15_RACE_CONDITION_FIX',
            timestamp: new Date().toISOString(),
            features: [
              'Progress Save/Load',
              '120-hour Timeout (5 days, for 20 problems)',
              'Race Condition Fix: Pending Lock + Auto Retry',
              'Detailed Error Logging and Classification',
              'Cron Job: Auto Cleanup Every 6 Hours',
              'Attention Check with Proper Lock',
              'Assignment Fingerprint',
              'Progress Archive',
              'Participant ID Verification',
              'R2 JSON File Access',
              'Fixed KV Lock TTL',
              'Participant ID in URL Assignment',
              'Worker redirects to Pages for HTML',
              'Admin Dashboard with HTTP Basic Auth',
              'Admin API: Stats, Assignments, Export, Download, Reassign',
              'Critical Fix: Attention Check Lock Race Condition',
              'Complete Timeout Recycling (update session_ status, delete used_, archive progress_)',
              'Fixed Admin Download (result_id from assignment)',
              'Session Timeout Status Preservation (status=timeout_locked instead of delete)',
              'Fixed Admin Stats (count from assignment_ instead of session_)',
              'Admin Manual Cleanup Button (calls cleanupTimeoutAssignments)',
              'Admin Timeout Status Display (show timeout_locked in table)',
              'Duplicate Request Prevention (5-second lock per participant_id)',
              'Extended Timeout: 48h → 120h (v2.5.14, for 20-question test)'
            ],
            cron: {
              enabled: true,
              schedule: '0 */6 * * *',
              description: 'Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)',
              note: 'Must be configured manually in Cloudflare Dashboard (Pages does not support Cron in wrangler.toml)'
            }
          }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' }
          });

        case '/api/health':
          // 健康检查端点
          if (request.method === 'GET') {
            return await handleHealth(request, corsHeaders, env);
          }
          break;

        case '/api/test-data':
          // 测试数据端点
          if (request.method === 'GET') {
            return await handleTestData(request, corsHeaders, env);
          }
          break;

        case '/api/get_test_groups':
          // 获取测试组列表（兼容性端点）
          if (request.method === 'GET') {
            return await handleTestGroups(corsHeaders, env);
          }
          break;

        case '/api/save_results':
          // 保存结果（兼容性端点，映射到 submit_results）
          if (request.method === 'POST') {
            return await handleSaveResults(request, corsHeaders, env);
          }
          break;

        // 注释：静态页面路由已移除，由 env.ASSETS.fetch() 在 default case 处理

        default:
          // 检查是否是 /api/admin/download/<url_id>
          if (url.pathname.startsWith('/api/admin/download/')) {
            if (!checkBasicAuth(request, env)) {
              return new Response('Unauthorized', {
                status: 401,
                headers: {
                  ...corsHeaders,
                  'WWW-Authenticate': 'Basic realm="Admin Area"'
                }
              });
            }
            const urlId = url.pathname.substring('/api/admin/download/'.length);
            return await handleAdminDownload(request, corsHeaders, env, urlId);
          }

          // 检查是否是 /api/admin/reassign/<url_id>
          if (url.pathname.startsWith('/api/admin/reassign/')) {
            if (request.method === 'POST') {
              if (!checkBasicAuth(request, env)) {
                return new Response('Unauthorized', {
                  status: 401,
                  headers: {
                    ...corsHeaders,
                    'WWW-Authenticate': 'Basic realm="Admin Area"'
                  }
                });
              }
              const urlId = url.pathname.substring('/api/admin/reassign/'.length);
              return await handleAdminReassign(request, corsHeaders, env, urlId);
            }
          }

          // 🆕 v2.5.11: 检查是否是 /api/admin/cleanup_duplicates
          if (url.pathname === '/api/admin/cleanup_duplicates') {
            if (request.method === 'POST') {
              if (!checkBasicAuth(request, env)) {
                return new Response('Unauthorized', {
                  status: 401,
                  headers: {
                    ...corsHeaders,
                    'WWW-Authenticate': 'Basic realm="Admin Area"'
                  }
                });
              }
              return await handleCleanupDuplicates(request, corsHeaders, env);
            }
          }

          // 检查是否是 /json/<path> 或 /test/<filename>.json 格式的路径(从R2 获取)
          if (url.pathname.startsWith('/json/') || 
              (url.pathname.startsWith('/test/') && url.pathname.endsWith('.json'))) {
            return await handleJsonFile(request, corsHeaders, env);
          }
          
          // 注释：移除了 /test/ 路径的特殊处理
          // 因为在 Advanced Mode 中，静态文件应该由 env.ASSETS.fetch() 处理
          
          return new Response('API endpoint not found', { 
            status: 404,
            headers: corsHeaders 
          });
      }

      // 对于非API请求，返回静态资产
      // 这是 Advanced Mode 的关键：必须显式处理静态文件
      console.log(`[Static Asset] Fetching: ${url.pathname}${url.search}`);
      const assetResponse = await env.ASSETS.fetch(request);
      console.log(`[Static Asset] Response status: ${assetResponse.status}`);
      return assetResponse;

    } catch (error) {
      console.error('API Error:', error);
      return new Response(JSON.stringify({ 
        error: 'Internal server error: ' + error.message 
      }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
  },

  // ========================================
  // 🕐 Cron Job: 定时清理超时的 URL 分配
  // ========================================
  // 每 6 小时执行一次，自动扫描并回收超过 48 小时的分配
  async scheduled(event, env, ctx) {
    console.log('🕐 [CRON] Starting scheduled timeout cleanup...');
    console.log(`   Trigger time: ${new Date(event.scheduledTime).toISOString()}`);
    console.log(`   Cron pattern: ${event.cron}`);
    
    try {
      const cleanupResult = await cleanupTimeoutAssignments(env);
      
      console.log('✅ [CRON] Cleanup completed successfully');
      console.log(`   Cleaned up: ${cleanupResult.cleaned_count} assignments`);
      console.log(`   Errors: ${cleanupResult.error_count}`);
      console.log(`   Duration: ${cleanupResult.duration_ms}ms`);
      
      // 记录清理结果到 KV（用于审计）
      const logKey = `cleanup_log_${new Date(event.scheduledTime).toISOString().replace(/[:.]/g, '')}`;
      await env.ARC_DATA.put(logKey, JSON.stringify({
        ...cleanupResult,
        trigger_time: new Date(event.scheduledTime).toISOString(),
        cron_pattern: event.cron
      }), {
        expirationTtl: 60 * 60 * 24 * 30 // 保留 30 天
      });
      
    } catch (error) {
      console.error('❌ [CRON] Cleanup failed:', error);
      
      // 记录错误到 KV
      const errorKey = `cleanup_error_${new Date(event.scheduledTime).toISOString().replace(/[:.]/g, '')}`;
      await env.ARC_DATA.put(errorKey, JSON.stringify({
        error: error.message,
        stack: error.stack,
        trigger_time: new Date(event.scheduledTime).toISOString()
      }), {
        expirationTtl: 60 * 60 * 24 * 30 // 保留 30 天
      });
    }
  }
};

// 处理JSON文件上传
async function handleUpload(request, corsHeaders) {
  try {
    const formData = await request.formData();
    const file = formData.get('file');
    
    if (!file) {
      return new Response(JSON.stringify({ error: 'No file provided' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 验证文件类型
    if (!file.name.endsWith('.json')) {
      return new Response(JSON.stringify({ error: 'Only JSON files are allowed' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    const text = await file.text();
    const jsonData = JSON.parse(text);
    
    // 验证JSON结构
    if (!jsonData || typeof jsonData !== 'object') {
      throw new Error('Invalid JSON structure');
    }

    // 可选：保存到KV 存储用于后续访问
    // await env.ARC_DATA.put(`uploaded_${Date.now()}.json`, text);

    return new Response(JSON.stringify({ 
      success: true, 
      message: 'File uploaded successfully',
      filename: file.name,
      data: jsonData
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      error: 'Failed to process file: ' + error.message 
    }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 获取当前加载的问题数据
async function handleGetProblems(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session_id');
    const testGroup = url.searchParams.get('group');
    
    let data = null;
    
    // 如果有 session_id，从 session 的 cache 中获取
    if (sessionId) {
      const cacheKey = `session_data_${sessionId}`;
      const cachedData = await env.ARC_DATA.get(cacheKey);
      
      if (cachedData) {
        console.log(`[handleGetProblems] Found cached data for session: ${sessionId}`);
        data = JSON.parse(cachedData);
        
        return new Response(JSON.stringify({ 
          success: true, 
          data: data,
          source: 'session_cache'
        }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      } else {
        console.log(`[handleGetProblems] No cached data for session: ${sessionId}, returning empty`);
        // 返回空数据，让前端使用 window.currentData
        return new Response(JSON.stringify({ 
          success: false,
          error: 'No cached data for session. Use window.currentData instead.',
          hint: 'Data should be loaded via /api/load_remote_json first'
        }), {
          status: 404,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }
    
    // 如果指定了测试组,从存储中获取
    if (testGroup && env.ARC_DATA) {
      const stored = await env.ARC_DATA.get(testGroup);
      if (stored) {
        data = JSON.parse(stored);
      }
    }
    
    // 如果没有数据，返回错误
    if (!data) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'No data available. Please load JSON data first.',
        hint: 'Use /api/load_remote_json or provide session_id/group parameter'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    return new Response(JSON.stringify({ 
      success: true, 
      data: data,
      source: testGroup ? 'group_storage' : 'unknown'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to get problems: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理获取 tutorials 请求
async function handleGetTutorials(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session_id');
    
    // 如果有 session_id，从 session 的 cache 中获取
    if (sessionId) {
      const cacheKey = `session_data_${sessionId}`;
      const cachedData = await env.ARC_DATA.get(cacheKey);
      
      if (cachedData) {
        console.log(`[handleGetTutorials] Found cached data for session: ${sessionId}`);
        const data = JSON.parse(cachedData);
        
        // 只返回 tutorials 部分
        return new Response(JSON.stringify({ 
          success: true, 
          data: { tutorials: data.tutorials || data.Tutorials || [] },
          source: 'session_cache'
        }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }
    
    // 没有缓存数据，返回错误提示使用 window.currentData
    return new Response(JSON.stringify({ 
      success: false,
      error: 'No cached data for session. Use window.currentData instead.',
      hint: 'Data should be loaded via /api/load_remote_json first'
    }), {
      status: 404,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to get tutorials: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// ========================================
// 超时检查工具函数
// ========================================

/**
 * 检查URL分配是否超时（120小时限制，适用于20道题）
 * @param {Object} assignment - 分配记录对象
 * @param {number} timeoutHours - 超时小时数（默认120小时，即5天）
 * @returns {Object} - {is_timeout: boolean, status: string, timeout_at?: string, time_remaining?: string}
 */
function checkUrlTimeout(assignment, timeoutHours = 120) {
  // 如果已经是超时锁定状态
  if (assignment.status === 'timeout_locked') {
    return {
      is_timeout: true,
      status: 'timeout_locked',
      timeout_at: assignment.timeout_at
    };
  }
  
  // 如果已完成，不检查超时
  if (assignment.status === 'completed') {
    return {
      is_timeout: false,
      status: 'completed'
    };
  }
  
  // 获取分配时间（优先使用 assigned_at，回退到 created_at）
  const assignedAtStr = assignment.assigned_at || assignment.created_at;
  
  if (!assignedAtStr) {
    console.warn('⚠️ Assignment missing both assigned_at and created_at, cannot check timeout');
    return {
      is_timeout: false,
      status: assignment.status || 'assigned',
      warning: 'missing_timestamp'
    };
  }
  
  // 检查是否超时
  const assignedAt = new Date(assignedAtStr);
  const currentTime = new Date();
  const timeoutMs = timeoutHours * 60 * 60 * 1000; // 转换为毫秒
  const elapsedMs = currentTime.getTime() - assignedAt.getTime();
  
  if (elapsedMs > timeoutMs) {
    // 超时了
    return {
      is_timeout: true,
      status: 'timeout_locked',
      timeout_at: currentTime.toISOString(),
      elapsed_hours: (elapsedMs / (60 * 60 * 1000)).toFixed(2)
    };
  }
  
  // 未超时
  const remainingMs = timeoutMs - elapsedMs;
  const remainingHours = (remainingMs / (60 * 60 * 1000)).toFixed(2);
  
  return {
    is_timeout: false,
    status: assignment.status || 'assigned',
    time_remaining: `${remainingHours} hours`,
    elapsed_hours: (elapsedMs / (60 * 60 * 1000)).toFixed(2)
  };
}

// 提交测试结果
async function handleSubmitResults(request, corsHeaders, env) {
  try {
    const results = await request.json();
    
    // 提取关键信息
    const sessionId = results.sessionId || results.session_id;
    const assignmentFingerprint = results.assignmentFingerprint || results.assignment_fingerprint;
    
    if (!sessionId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'session_id_required',
        message: '缺少 session_id'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 获取分配记录进行验证
    const assignmentJson = await env.ARC_DATA.get(`assignment_${sessionId}`);
    
    if (!assignmentJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'invalid_url',
        message: 'URL未分配或无效'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    
    console.log(`📋 [SUBMIT CHECK] Session: ${sessionId}`);
    console.log(`   Status: ${assignment.status}`);
    console.log(`   Locked: ${assignment.locked}`);
    console.log(`   Fingerprint: ${assignment.assignment_fingerprint}`);
    console.log(`   Completed At: ${assignment.completed_at || 'null'}`);
    console.log(`   Failed At: ${assignment.attention_check_failed_at || 'null'}`);
    
    // 🕐 检查URL是否超时（48小时限制）
    const timeoutCheck = checkUrlTimeout(assignment);
    if (timeoutCheck.is_timeout) {
      console.log(`⏰ [REJECT] Session ${sessionId} has timed out - rejecting submission and recycling URL`);
      
      // 如果还未标记为超时，现在标记并回收
      if (assignment.status !== 'timeout_locked') {
        assignment.status = 'timeout_locked';
        assignment.timeout_at = new Date().toISOString();
        await env.ARC_DATA.put(`assignment_${sessionId}`, JSON.stringify(assignment));
        
        // 🗄️v2.4.0: 超时后归档进度文件
        await archiveSavedProgress(env, sessionId, results.userNickname || results.user_nickname || assignment.participant_id, 'timeout');
        
        // 🔄 回收超时的URL：更新 session_ 状态、删除 used_ 键、归档 progress_
        const testGroup = assignment.test_group_file || assignment.test_group;
        
        // 更新 session_ 状态为 timeout_locked（保留记录而非删除）
        const sessionKey = `session_${sessionId}`;
        const sessionJson = await env.ARC_DATA.get(sessionKey);
        if (sessionJson) {
          const session = JSON.parse(sessionJson);
          session.status = 'timeout_locked';
          session.timeout_at = assignment.timeout_at;
          await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
          console.log(`  ✓ Updated session_${sessionId} status to timeout_locked`);
        }
        
        if (testGroup) {
          await env.ARC_DATA.delete(`used_${testGroup}`);
          console.log(`  ✓ Deleted used_${testGroup} - test group released`);
        }
        
        // 归档 progress_ 键而不是直接删除
        const progressKey = `progress_${sessionId}`;
        const progressData = await env.ARC_DATA.get(progressKey);
        if (progressData) {
          const archiveKey = `progress_archived_${sessionId}_timeout_${assignment.timeout_at.replace(/[:.]/g, '')}`;
          await env.ARC_DATA.put(archiveKey, progressData);
          await env.ARC_DATA.delete(progressKey);
          console.log(`  ✓ Archived progress_${sessionId} → ${archiveKey}`);
        }
      }
      
      return new Response(JSON.stringify({ 
        success: false,
        error: 'assignment_timeout',
        message: 'Your assignment has expired (48-hour limit exceeded). Submission is no longer allowed.',
        timeout_at: timeoutCheck.timeout_at,
        status: 'timeout_locked'
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 验证分配指纹（如果提供）
    if (assignmentFingerprint) {
      const storedFingerprint = assignment.assignment_fingerprint;
      if (storedFingerprint && storedFingerprint !== assignmentFingerprint) {
        return new Response(JSON.stringify({ 
          success: false,
          error: 'fingerprint_mismatch',
          message: '分配指纹不匹配，该URL可能已被重新分配或已失效',
          detail: `当前分配时间: ${assignment.assigned_at || '未知'}`
        }), {
          status: 403,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }
    
    // 🔒 检查是否被锁定（attention check失败）
    if (assignment.locked || assignment.status === 'attention_check_failed') {
      console.log(`🚫 [REJECT] Session ${sessionId} is LOCKED`);
      console.log(`   Reason: Attention Check Failed`);
      console.log(`   Locked Flag: ${assignment.locked}`);
      console.log(`   Status: ${assignment.status}`);
      return new Response(JSON.stringify({ 
        success: false,
        error: 'assignment_locked',
        message: '该分配已被锁定（Attention Check失败），不允许提交',
        failed_at: assignment.attention_check_failed_at,
        assignment_fingerprint: assignment.assignment_fingerprint,
        status: assignment.status,
        locked: assignment.locked
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 检查是否已经完成
    if (assignment.status === 'completed') {
      console.log(`🚫 [REJECT] Session ${sessionId} already COMPLETED at ${assignment.completed_at}`);
      return new Response(JSON.stringify({ 
        success: false,
        error: 'already_completed',
        message: '测试已经完成，不允许重复提交',
        completed_at: assignment.completed_at
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 添加时间戳和唯一ID
    const timestamp = new Date().toISOString();
    const resultId = `arc_results_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    console.log(`✅ [ACCEPT] Session ${sessionId} passed all checks, saving results...`);
    console.log(`   Result ID: ${resultId}`);
    
    const resultData = {
      id: resultId,
      timestamp: timestamp,
      session_id: sessionId,
      assignment_fingerprint: assignmentFingerprint,
      test_group: assignment.test_group_file,
      ...results
    };

    // 更新分配状态为完成，并保存正确率信息
    assignment.status = 'completed';
    assignment.completed_at = timestamp;
    assignment.result_id = resultId;
    
    // 🎯v2.5.4: 保存正确率信息到 assignment（用于 Admin 面板显示）
    if (results.correctAnswersCount !== undefined && results.totalProblems !== undefined) {
      assignment.correct_answer = results.correctAnswersCount;
      assignment.total_questions = results.totalProblems;
      assignment.accuracy = ((results.correctAnswersCount / results.totalProblems) * 100).toFixed(1) + '%';
    } else if (results.correct_answer !== undefined && results.total_questions !== undefined) {
      assignment.correct_answer = results.correct_answer;
      assignment.total_questions = results.total_questions;
      assignment.accuracy = ((results.correct_answer / results.total_questions) * 100).toFixed(1) + '%';
    }
    
    await env.ARC_DATA.put(`assignment_${sessionId}`, JSON.stringify(assignment));

    // 保存结果到Cloudflare KV 存储
    if (env.ARC_RESULTS) {
      await env.ARC_RESULTS.put(resultId, JSON.stringify(resultData));
      console.log(`✓Results saved with ID: ${resultId} (fingerprint: ${assignmentFingerprint})`);
    }

    // 可选：保存到R2 存储桶用于长期存储
    if (env.ARC_BUCKET) {
      await env.ARC_BUCKET.put(`results/${resultId}.json`, JSON.stringify(resultData, null, 2));
    }

    // 🗄️v2.4.0: 提交成功后归档进度文件
    await archiveSavedProgress(env, sessionId, results.userNickname || results.user_nickname, 'submitted');

    return new Response(JSON.stringify({ 
      success: true, 
      message: 'Results saved successfully',
      resultId: resultId,
      timestamp: timestamp
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Submit results error:', error);
    return new Response(JSON.stringify({ 
      error: 'Failed to save results: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理 Attention Check 失败
async function handleAttentionCheckFailed(request, corsHeaders, env) {
  try {
    const data = await request.json();
    const sessionId = data.session_id || data.sessionId;
    const assignmentFingerprint = data.assignment_fingerprint || data.assignmentFingerprint;
    const failureData = data.failure_data || {};
    
    if (!sessionId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'missing_session_id',
        message: 'Session ID is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 获取分配记录
    const assignmentJson = await env.ARC_DATA.get(`assignment_${sessionId}`);
    
    if (!assignmentJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'invalid_url',
        message: 'URL未分配或无效'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    
    // 验证分配指纹（如果提供）
    if (assignmentFingerprint) {
      const storedFingerprint = assignment.assignment_fingerprint;
      if (storedFingerprint && storedFingerprint !== assignmentFingerprint) {
        return new Response(JSON.stringify({ 
          success: false,
          error: 'fingerprint_mismatch',
          message: '分配指纹不匹配，该URL可能已被重新分配',
          detail: `当前分配时间: ${assignment.assigned_at || '未知'}`
        }), {
          status: 403,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }
    
    // 检查是否已经标记为失败
    if (assignment.status === 'attention_check_failed') {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'already_failed',
        message: 'Attention check已经标记为失败',
        failed_at: assignment.attention_check_failed_at
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 检查是否已经完成测试（不允许失败后再完成）
    if (assignment.status === 'completed') {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'already_completed',
        message: '测试已完成，不能标记为失败'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 标记 attention check 失败
    const failedAt = new Date().toISOString();
    assignment.status = 'attention_check_failed';
    assignment.attention_check_failed_at = failedAt;
    assignment.locked = true;  // 锁定此分配，防止后续提交
    assignment.failure_data = failureData;
    
    // ⚠️ 关键：先保存更新后的分配记录，确保状态立即生效
    await env.ARC_DATA.put(`assignment_${sessionId}`, JSON.stringify(assignment));
    console.log(`� Assignment ${sessionId} locked: status=${assignment.status}, locked=${assignment.locked}`);
    
    // �🔧 显式释放测试组（删除 used_ 标记，与 Flask 逻辑一致）
    const testGroup = assignment.test_group_file;
    await env.ARC_DATA.delete(`used_${testGroup}`);
    
    // 🔧 同时更新 session 状态
    const sessionKey = `session_${sessionId}`;
    const sessionJson = await env.ARC_DATA.get(sessionKey);
    if (sessionJson) {
      const session = JSON.parse(sessionJson);
      session.status = 'attention_check_failed';
      session.failed_at = failedAt;
      await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
    }
    
    // 🗄️v2.4.0: 注意力检查失败后归档进度文件
    const userNickname = failureData.user_nickname || failureData.userNickname || assignment.participant_id;
    await archiveSavedProgress(env, sessionId, userNickname, 'attention_check_failed');
    
    console.log(`⚠️ Marked attention check failed for URL: ${sessionId}, test group ${testGroup} released (fingerprint: ${assignmentFingerprint})`);
    
    return new Response(JSON.stringify({ 
      success: true,
      message: 'Attention check标记为失败，测试组已释放',
      locked_at: failedAt
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Attention check failed error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to mark attention check as failed: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理再分配请求
async function handleReassignUrl(request, corsHeaders, env) {
  try {
    const data = await request.json();
    const urlId = data.url_id || data.urlId || data.session_id;
    
    if (!urlId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'missing_url_id',
        message: 'URL ID is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 获取分配记录
    const assignmentJson = await env.ARC_DATA.get(`assignment_${urlId}`);
    
    if (!assignmentJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'url_not_found',
        message: '未找到指定的URL分配记录'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    
    // 检查是否已完成
    if (assignment.status !== 'completed') {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'not_completed',
        message: '该URL尚未完成测试，无法再分配'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const testGroup = assignment.test_group_file;
    
    // 获取历史记录
    let assignmentHistory = await getAssignmentHistory(env, urlId);
    
    // 将已完成的分配保存到历史记录
    assignmentHistory.push({
      fingerprint: assignment.assignment_fingerprint,
      test_group: assignment.test_group_file,
      participant_id: assignment.participant_id,
      assigned_at: assignment.assigned_at,
      completed_at: assignment.completed_at,
      status: 'completed_then_reassigned',
      reassigned_at: new Date().toISOString()
    });
    
    // 保存历史记录
    await saveAssignmentHistory(env, urlId, assignmentHistory);
    
    // 标记此URL 为已再分配"状态，允许重新分配
    assignment.status = 'reassigned';
    assignment.reassigned_at = new Date().toISOString();
    assignment.locked = false;
    
    // 保存更新后的分配记录
    await env.ARC_DATA.put(`assignment_${urlId}`, JSON.stringify(assignment));
    
    // 将测试组标记为可用
    await env.ARC_DATA.delete(`used_${testGroup}`);
    
    console.log(`📝 URL ${urlId} marked as 'reassigned', test group '${testGroup}' released, ready for new assignment`);
    
    return new Response(JSON.stringify({ 
      success: true,
      message: `成功将测试组 "${testGroup}" 重新加入未分配列表，URL 已标记为可再分配`,
      test_group: testGroup
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Reassign URL error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to reassign URL: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理重置所有分配请求
async function handleResetAllAssignments(request, corsHeaders, env) {
  try {
    console.log('🔄 Starting reset of all assignments...');
    
    let resetCount = 0;
    let lockedCleared = 0;
    let failedCleared = 0;
    let sessionCount = 0;
    const resetTimestamp = new Date().toISOString();
    
    // 保存重置记录（用于追踪重置历史）
    const resetRecord = {
      timestamp: resetTimestamp,
      reset_count: 0,
      locked_cleared: 0,
      failed_cleared: 0,
      session_cleared: 0
    };
    
    // 获取所有assignment keys
    const assignmentList = await env.ARC_DATA.list({ prefix: 'assignment_' });
    
    // 统计并删除所有分配记录
    for (const key of assignmentList.keys) {
      const urlId = key.name.replace('assignment_', '');
      const assignmentJson = await env.ARC_DATA.get(key.name);
      
      if (assignmentJson) {
        const assignment = JSON.parse(assignmentJson);
        const testGroup = assignment.test_group_file;
        
        // 统计锁定状态
        if (assignment.locked) {
          lockedCleared++;
        }
        
        // 统计失败状态
        if (assignment.status === 'attention_check_failed') {
          failedCleared++;
        }
        
        // 删除 assignment 记录
        await env.ARC_DATA.delete(key.name);
        
        // 删除 used_ 标记（释放测试组）
        await env.ARC_DATA.delete(`used_${testGroup}`);
        
        resetCount++;
      }
    }
    
    // 删除所有completed记录
    const completedList = await env.ARC_DATA.list({ prefix: 'completed_' });
    const completedCount = completedList.keys.length;
    for (const key of completedList.keys) {
      await env.ARC_DATA.delete(key.name);
    }
    
    // 删除所有failed记录
    const failedList = await env.ARC_DATA.list({ prefix: 'failed_' });
    for (const key of failedList.keys) {
      await env.ARC_DATA.delete(key.name);
    }
    
    // 删除所有历史记录
    const historyList = await env.ARC_DATA.list({ prefix: 'assignment_history_' });
    for (const key of historyList.keys) {
      await env.ARC_DATA.delete(key.name);
    }
    
    // 删除所有used_标记
    const usedList = await env.ARC_DATA.list({ prefix: 'used_' });
    for (const key of usedList.keys) {
      await env.ARC_DATA.delete(key.name);
    }
    
    // � 删除所有session记录
    const sessionList = await env.ARC_DATA.list({ prefix: 'session_' });
    for (const key of sessionList.keys) {
      await env.ARC_DATA.delete(key.name);
      sessionCount++;
    }
    
    // �🗄️v2.4.0: 备份并清理所有进度文件
    let progressCount = 0;
    let progressArchivedCount = 0;
    const progressList = await env.ARC_DATA.list({ prefix: 'progress_' });
    
    for (const key of progressList.keys) {
      // 跳过已归档的进度文件
      if (key.name.startsWith('progress_archived_')) {
        continue;
      }
      
      // 读取进度数据
      const progressJson = await env.ARC_DATA.get(key.name);
      if (progressJson) {
        // 生成备份键名
        const progressKey = key.name.replace('progress_', '');
        const backupKey = `progress_archived_${progressKey}_reset_${resetTimestamp.replace(/[:.]/g, '')}`;
        
        // 备份进度文件
        await env.ARC_DATA.put(backupKey, progressJson);
        progressArchivedCount++;
        
        // 删除原始进度文件
        await env.ARC_DATA.delete(key.name);
        progressCount++;
      }
    }
    
    // 🗄️v2.5.2: 归档并清理 ARC_RESULTS namespace 中的所有结果
    let resultsCount = 0;
    let resultsArchivedCount = 0;
    
    if (env.ARC_RESULTS) {
      console.log('🗄️ Starting to archive ARC_RESULTS...');
      
      // 列出所有结果（不使用 prefix，因为可能有不同的键名格式）
      const resultsList = await env.ARC_RESULTS.list();
      
      for (const key of resultsList.keys) {
        // 跳过已归档的结果
        if (key.name.startsWith('archived_result_')) {
          continue;
        }
        
        // 读取结果数据
        const resultJson = await env.ARC_RESULTS.get(key.name);
        if (resultJson) {
          // 生成归档键名
          const archiveKey = `archived_result_${key.name}_reset_${resetTimestamp.replace(/[:.]/g, '')}`;
          
          // 归档到 ARC_RESULTS namespace（保留在同一个 namespace）
          await env.ARC_RESULTS.put(archiveKey, resultJson);
          resultsArchivedCount++;
          
          // 删除原始结果
          await env.ARC_RESULTS.delete(key.name);
          resultsCount++;
          
          console.log(`  ✓ Archived result: ${key.name} → ${archiveKey}`);
        }
      }
      
      console.log(`✓ ARC_RESULTS 归档完成: ${resultsCount} 个结果已归档`);
    } else {
      console.log('⚠️ ARC_RESULTS namespace not available');
    }
    
    // 🗄️v2.5.2: 归档并清理 R2 Bucket 中的 results/ 文件夹
    let r2ResultsCount = 0;
    let r2ResultsArchivedCount = 0;
    
    if (env.ARC_BUCKET) {
      console.log('🗄️ Starting to archive R2 results folder...');
      
      try {
        // 列出 results/ 文件夹中的所有文件
        const r2ResultsList = await env.ARC_BUCKET.list({ prefix: 'results/' });
        
        if (r2ResultsList.objects && r2ResultsList.objects.length > 0) {
          // 生成备份文件夹名称（带时间戳）
          const backupFolderName = `results_backup_${resetTimestamp.replace(/[:.]/g, '_').replace(/T/g, '_').replace(/-/g, '')}`;
          
          console.log(`  📁 Creating backup folder: ${backupFolderName}/`);
          
          for (const obj of r2ResultsList.objects) {
            try {
              // 读取原文件
              const fileContent = await env.ARC_BUCKET.get(obj.key);
              
              if (fileContent) {
                // 生成备份路径（将 results/ 替换为 results_backup_xxx/）
                const backupKey = obj.key.replace('results/', `${backupFolderName}/`);
                
                // 写入备份
                await env.ARC_BUCKET.put(backupKey, fileContent.body);
                r2ResultsArchivedCount++;
                
                // 删除原文件
                await env.ARC_BUCKET.delete(obj.key);
                r2ResultsCount++;
                
                console.log(`  ✓ Archived R2 file: ${obj.key} → ${backupKey}`);
              }
            } catch (fileError) {
              console.error(`  ✗ Error archiving file ${obj.key}:`, fileError.message);
            }
          }
          
          console.log(`✓ R2 results 归档完成: ${r2ResultsCount} 个文件已归档到 ${backupFolderName}/`);
        } else {
          console.log('  ℹ️ No files found in results/ folder');
        }
      } catch (r2Error) {
        console.error('⚠️ Error accessing R2 bucket:', r2Error.message);
      }
    } else {
      console.log('⚠️ ARC_BUCKET not available');
    }
    
    // 保存重置记录到KV（用于追踪重置历史）
    resetRecord.reset_count = resetCount;
    resetRecord.locked_cleared = lockedCleared;
    resetRecord.failed_cleared = failedCleared;
    resetRecord.completed_count = completedCount;
    resetRecord.session_cleared = sessionCount;
    resetRecord.progress_cleared = progressCount;
    resetRecord.progress_archived = progressArchivedCount;
    resetRecord.results_cleared = resultsCount;
    resetRecord.results_archived = resultsArchivedCount;
    resetRecord.r2_results_cleared = r2ResultsCount;
    resetRecord.r2_results_archived = r2ResultsArchivedCount;
    
    await env.ARC_DATA.put(`reset_record_${resetTimestamp}`, JSON.stringify(resetRecord));
    
    console.log(`✓重置完成：`);
    console.log(`   - ${resetCount} 个URL已重置为未分配状态`);
    console.log(`   - ${lockedCleared} 个锁定记录已清除`);
    console.log(`   - ${failedCleared} 个失败记录已清除`);
    console.log(`   - ${completedCount} 个完成记录已清除`);
    console.log(`   - ${sessionCount} 个session记录已清除`);
    console.log(`   - ${progressCount} 个进度文件已备份并清除`);
    console.log(`   - ${resultsCount} 个KV结果已归档并清除`);
    console.log(`   - ${r2ResultsCount} 个R2结果文件已归档并清除`);
    console.log(`   - 所有历史记录已清除`);
    console.log(`   - 重置记录已保存 reset_record_${resetTimestamp}`);
    
    // 🔧 重新初始化 available_test_groups 列表
    console.log('🔧 Re-initializing available_test_groups...');
    const listed = await env.ARC_BUCKET.list({ prefix: 'test/' });
    const allTestGroups = listed.objects
      .map(obj => obj.key.replace('test/', ''))
      .filter(name => name.match(/^test_group\d+\.json$/));
    await env.ARC_DATA.put('available_test_groups', JSON.stringify(allTestGroups));
    console.log(`   ✓ Initialized available_test_groups with ${allTestGroups.length} groups`);
    
    return new Response(JSON.stringify({ 
      success: true,
      message: `成功重置了 ${resetCount} 个URL，${sessionCount} 个session，${progressArchivedCount} 个进度文件已备份，${resultsArchivedCount} 个KV结果已归档，${r2ResultsArchivedCount} 个R2结果文件已归档`,
      reset_count: resetCount,
      locked_cleared: lockedCleared,
      failed_cleared: failedCleared,
      session_cleared: sessionCount,
      progress_cleared: progressCount,
      progress_archived: progressArchivedCount,
      results_cleared: resultsCount,
      results_archived: resultsArchivedCount,
      r2_results_cleared: r2ResultsCount,
      r2_results_archived: r2ResultsArchivedCount,
      reset_timestamp: resetTimestamp,
      reset_record_key: `reset_record_${resetTimestamp}`,
      before_stats: {
        assigned_count: resetCount,
        completed_count: completedCount,
        failed_count: failedCleared,
        session_count: sessionCount,
        progress_count: progressCount,
        results_count: resultsCount,
        r2_results_count: r2ResultsCount
      },
      after_stats: {
        assigned_count: 0,
        completed_count: 0,
        failed_count: 0,
        session_count: 0,
        progress_count: 0,
        results_count: 0,
        r2_results_count: 0
      }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Reset all assignments error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      message: '重置失败: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 列出可用的JSON文件
async function handleListJsonFiles(request, corsHeaders, env) {
  try {
    let files = [];
    
    // 从R2 存储桶获取文件列表
    if (env.ARC_BUCKET) {
      const objects = await env.ARC_BUCKET.list({ prefix: 'test/' });
      
      files = objects.objects
        .filter(obj => obj.key.endsWith('.json'))
        .map(obj => ({
          name: obj.key.split('/').pop(),
          path: obj.key,
          url: `/json/${obj.key}`,
          full_url: `${new URL(request.url).origin}/json/${obj.key}`,
          size: obj.size,
          modified: obj.uploaded
        }));
    } else {
      // 静态文件列表（如果没有R2存储）
      files = [
        {
          name: 'test_group1.json',
          path: 'test/test_group1.json',
          url: '/test/test_group1.json',
          full_url: `${new URL(request.url).origin}/test/test_group1.json`
        },
        {
          name: 'test_group2.json', 
          path: 'test/test_group2.json',
          url: '/test/test_group2.json',
          full_url: `${new URL(request.url).origin}/test/test_group2.json`
        }
        // 添加更多静态文件..
      ];
    }

    return new Response(JSON.stringify({ 
      success: true, 
      files: files 
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      error: 'Failed to list files: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 获取测试组列表
async function handleTestGroups(corsHeaders, env) {
  try {
    let testGroups = [];
    
    // 从KV存储获取预加载的测试组
    if (env.ARC_DATA) {
      const keys = await env.ARC_DATA.list();
      testGroups = keys.keys
        .filter(key => key.name.startsWith('test_group'))
        .map(key => ({
          name: key.name,
          filename: key.name + '.json'
        }));
    }
    
    return new Response(JSON.stringify({ 
      success: true, 
      test_groups: testGroups 
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      error: 'Failed to get test groups: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 加载远程JSON文件
async function handleLoadRemoteJson(request, corsHeaders, env) {
  try {
    const { url: jsonUrl } = await request.json();
    
    if (!jsonUrl) {
      console.error(`[handleLoadRemoteJson] No URL provided in request`);
      return new Response(JSON.stringify({ 
        success: false,
        error: 'No URL provided' 
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    console.log(`[handleLoadRemoteJson] Loading JSON from: ${jsonUrl}`);

    // 检查是否是内部路径（/test/xxx.json 或 /json/xxx）
    if (jsonUrl.startsWith('/test/') || jsonUrl.startsWith('/json/')) {
      // 从 R2 直接获取文件
      let filePath;
      if (jsonUrl.startsWith('/json/')) {
        filePath = jsonUrl.substring(6); // 移除 '/json/'
      } else if (jsonUrl.startsWith('/test/')) {
        filePath = jsonUrl.substring(1); // 移除开头的 '/' -> 'test/xxx.json'
      }
      
      console.log(`[handleLoadRemoteJson] Fetching from R2: ${filePath}`);
      
      if (!env.ARC_BUCKET) {
        console.error(`[handleLoadRemoteJson] R2 bucket not configured`);
        return new Response(JSON.stringify({ 
          success: false,
          error: 'R2 bucket not configured' 
        }), {
          status: 503,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const object = await env.ARC_BUCKET.get(filePath);
      
      if (!object) {
        console.error(`[handleLoadRemoteJson] File not found in R2: ${filePath}`);
        return new Response(JSON.stringify({ 
          success: false,
          error: 'File not found: ' + filePath 
        }), {
          status: 404,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const text = await object.text();
      const data = JSON.parse(text);
      
      console.log(`[handleLoadRemoteJson] Successfully loaded from R2: ${filePath}`);
      
      // 直接返回原始 JSON 数据，不做格式转换
      return new Response(JSON.stringify({ 
        success: true, 
        data: data,
        source: jsonUrl
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 如果是外部 URL，使用 fetch
    const response = await fetch(jsonUrl);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      // 尝试解析为JSON，即使Content-Type不是application/json
      const text = await response.text();
      const data = JSON.parse(text);
      
      return new Response(JSON.stringify({ 
        success: true, 
        data: data,
        source: jsonUrl
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    const data = await response.json();
    
    return new Response(JSON.stringify({ 
      success: true, 
      data: data,
      source: jsonUrl
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error(`[handleLoadRemoteJson] Error:`, error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to load remote JSON: ' + error.message 
    }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 从R2 bucket 获取 JSON 文件
async function handleJsonFile(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    
    // 处理 /json/ 和 /test/ 两种路径格式
    let filePath;
    if (url.pathname.startsWith('/json/')) {
      filePath = url.pathname.substring(6); // 移除 '/json/'
    } else if (url.pathname.startsWith('/test/')) {
      // /test/test_group1.json → test/test_group1.json (R2 中的实际路径)
      filePath = url.pathname.substring(1); // 移除开头的 '/'
    } else {
      return new Response(JSON.stringify({ 
        error: 'Invalid path format' 
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    console.log(`[handleJsonFile] Fetching from R2: ${filePath}`);
    
    if (!env.ARC_BUCKET) {
      return new Response(JSON.stringify({ 
        error: 'R2 bucket not configured' 
      }), {
        status: 503,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 从R2 获取文件
    const object = await env.ARC_BUCKET.get(filePath);
    
    if (!object) {
      console.error(`[handleJsonFile] File not found in R2: ${filePath}`);
      return new Response(JSON.stringify({ 
        error: 'File not found: ' + filePath 
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 读取文件内容
    const text = await object.text();
    
    // 尝试解析为JSON 以验证格式
    try {
      const data = JSON.parse(text);
      console.log(`[handleJsonFile] Successfully loaded: ${filePath}`);
      return new Response(JSON.stringify(data), {
        headers: { 
          ...corsHeaders, 
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=3600' // 缓存1小时
        }
      });
    } catch (parseError) {
      console.error(`[handleJsonFile] Invalid JSON: ${parseError.message}`);
      return new Response(JSON.stringify({ 
        error: 'Invalid JSON file: ' + parseError.message 
      }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

  } catch (error) {
    console.error(`[handleJsonFile] Error: ${error.message}`);
    return new Response(JSON.stringify({ 
      error: 'Failed to fetch file from R2: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理URL分配请求
async function handleGetAssignment(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session_id');
    
    if (!sessionId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'missing_session_id',
        message: 'Session ID is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 从KV存储获取分配信息
    const assignmentKey = `assignment_${sessionId}`;
    const assignmentJson = await env.ARC_DATA.get(assignmentKey);
    
    if (!assignmentJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'invalid_url',
        message: 'URL无效或已过期'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 🔧 解析并更新访问计数（与Flask 保持一致）
    const assignment = JSON.parse(assignmentJson);
    
    // 🕐 检查URL是否超时
    const timeoutCheck = checkUrlTimeout(assignment);
    if (timeoutCheck.is_timeout && assignment.status !== 'timeout_locked') {
      // 标记为超时并保存
      assignment.status = 'timeout_locked';
      assignment.timeout_at = timeoutCheck.timeout_at;
      console.log(`⏰ [TIMEOUT] Session ${sessionId} exceeded 48-hour limit - recycling URL`);
      
      // 🗄️v2.4.0: 超时后归档进度文件
      await archiveSavedProgress(env, sessionId, assignment.participant_id, 'timeout');
      
      // 🔄 回收超时的URL：更新 session_ 状态、删除 used_ 键、归档 progress_
      const testGroup = assignment.test_group_file || assignment.test_group;
      
      // 更新 session_ 状态为 timeout_locked（保留记录而非删除）
      const sessionKey = `session_${sessionId}`;
      const sessionJson = await env.ARC_DATA.get(sessionKey);
      if (sessionJson) {
        const session = JSON.parse(sessionJson);
        session.status = 'timeout_locked';
        session.timeout_at = timeoutCheck.timeout_at;
        await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
        console.log(`  ✓ Updated session_${sessionId} status to timeout_locked`);
      } else {
        console.log(`  ⚠️ session_${sessionId} not found, skipping update`);
      }
      
      // 删除 used_ 键（释放测试组供其他人使用）
      if (testGroup) {
        await env.ARC_DATA.delete(`used_${testGroup}`);
        console.log(`  ✓ Deleted used_${testGroup} - test group released`);
      }
      
      // 归档 progress_ 键（避免加载进度时报错，但保留数据）
      const progressKey = `progress_${sessionId}`;
      const progressData = await env.ARC_DATA.get(progressKey);
      if (progressData) {
        const archiveKey = `progress_archived_${sessionId}_timeout_${assignment.timeout_at.replace(/[:.]/g, '')}`;
        await env.ARC_DATA.put(archiveKey, progressData);
        await env.ARC_DATA.delete(progressKey);
        console.log(`  ✓ Archived progress_${sessionId} → ${archiveKey}`);
      } else {
        console.log(`  ℹ️ No progress data found for ${sessionId}`);
      }
      
      // 保存更新后的 assignment（标记为 timeout_locked）
      await env.ARC_DATA.put(assignmentKey, JSON.stringify(assignment));
      console.log(`  ✓ Assignment marked as timeout_locked and saved`);
      
      // 返回超时错误，不允许继续访问
      return new Response(JSON.stringify({ 
        success: false,
        error: 'assignment_timeout',
        message: 'Your assignment has expired (48-hour limit exceeded). The URL has been recycled.',
        timeout_at: timeoutCheck.timeout_at,
        elapsed_hours: timeoutCheck.elapsed_hours,
        status: 'timeout_locked'
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 🔒v2.5.2: 如果已经完成或锁定，不要更新访问信息（避免覆盖状态）
    // 这解决了提交后KV最终一致性导致的状态被覆盖问题
    if (assignment.status !== 'completed' && 
        assignment.status !== 'attention_check_failed' && 
        !assignment.locked) {
      assignment.access_count = (assignment.access_count || 0) + 1;
      assignment.last_access = new Date().toISOString();
      
      // 保存更新后的分配记录
      await env.ARC_DATA.put(assignmentKey, JSON.stringify(assignment));
      console.log(`✓Updated access count for session ${sessionId}: ${assignment.access_count}`);
    } else {
      console.log(`⚠️ Skipping access update for session ${sessionId} - status: ${assignment.status}, locked: ${assignment.locked}`);
    }

    // 为兼容性添加 test_group 别名
    const responseAssignment = {
      ...assignment,
      test_group: assignment.test_group_file  // test.html 期望这个字段
    };

    console.log('[handleGetAssignment] Returning assignment:', {
      session_id: responseAssignment.session_id,
      test_group: responseAssignment.test_group,
      test_group_file: responseAssignment.test_group_file
    });

    return new Response(JSON.stringify({
      success: true,
      assignment: responseAssignment
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to get assignment: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理验证参与者ID
async function handleVerifyParticipantId(request, corsHeaders, env) {
  try {
    const { participant_id, session_id } = await request.json();
    
    if (!participant_id) {
      return new Response(JSON.stringify({ 
        success: false,
        message: 'Participant ID is required' 
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 🚀 v2.5.19: 并行查询 progress 和 assignment（如果提供了 session_id）
    let hasSavedProgress = false;
    let savedProgressData = null;
    let hasAssignedUrl = false;
    let assignedUrlData = null;
    
    if (session_id) {
      // 如果提供了 session_id，并行查询 progress 和 assignment
      const [savedProgress, assignment] = await Promise.all([
        env.ARC_DATA.get(`progress_${participant_id}`),
        env.ARC_DATA.get(`assignment_${session_id}`)
      ]);
      
      // 处理 progress
      if (savedProgress) {
        savedProgressData = JSON.parse(savedProgress);
        hasSavedProgress = true;
      }
      
      // 处理 assignment
      if (assignment) {
        const assignmentData = JSON.parse(assignment);
        // 检测 completed 和 assigned 状态（排除 timeout_locked）
        if (assignmentData.participant_id === participant_id && 
            (assignmentData.status === 'completed' || assignmentData.status === 'assigned')) {
          hasAssignedUrl = true;
          assignedUrlData = assignmentData;
        }
      }
    } else {
      // 如果没有提供 session_id，需要查询 progress 并搜索所有 assignments
      // 🚀 v2.5.19: 先查询 progress，同时列出所有 assignments
      const [savedProgress, listResult] = await Promise.all([
        env.ARC_DATA.get(`progress_${participant_id}`),
        env.ARC_DATA.list({ prefix: 'assignment_' })
      ]);
      
      // 处理 progress
      if (savedProgress) {
        savedProgressData = JSON.parse(savedProgress);
        hasSavedProgress = true;
      }
      
      // 并行查询所有 assignment
      const assignmentPromises = listResult.keys.map(async (key) => {
        const assignment = await env.ARC_DATA.get(key.name);
        if (assignment) {
          const assignmentData = JSON.parse(assignment);
          // 检测 completed 和 assigned 状态（排除 timeout_locked、attention_check_failed、reassigned）
          if (assignmentData.participant_id === participant_id && 
              (assignmentData.status === 'completed' || assignmentData.status === 'assigned')) {
            return {
              session_id: key.name.replace('assignment_', ''),
              data: assignmentData,
              assigned_at: assignmentData.assigned_at || assignmentData.created_at
            };
          }
        }
        return null;
      });
      
      const results = await Promise.all(assignmentPromises);
      const matchedAssignments = results.filter(r => r !== null);
      
      // 如果有匹配的 assignment
      if (matchedAssignments.length > 0) {
        // 按时间排序（最早的在前）
        matchedAssignments.sort((a, b) => {
          const dateA = new Date(a.assigned_at || 0);
          const dateB = new Date(b.assigned_at || 0);
          return dateA.getTime() - dateB.getTime();  // 正序：最早的在前
        });
        
        hasAssignedUrl = true;
        assignedUrlData = matchedAssignments[0].data;  // 返回最早的
        
        // 🆕 如果发现重复（多个 assigned 状态），自动清理多余的
        // 🚀 v2.5.19: 优化为并行清理
        if (matchedAssignments.length > 1) {
          console.warn(`⚠️ [AUTO-CLEANUP] Participant ${participant_id} has ${matchedAssignments.length} assignments, auto-cleaning duplicates...`);
          
          // 保留最早的，并行清理其他的
          const cleanupPromises = matchedAssignments.slice(1).map(async (duplicate) => {
            const sessionId = duplicate.session_id;
            const testGroup = duplicate.data.test_group_file || duplicate.data.test_group;
            
            console.log(`  ❌ Auto-cleaning duplicate: ${sessionId} (${testGroup}, assigned at ${duplicate.assigned_at})`);
            
            const operations = [];
            
            // 1️⃣ 释放测试组
            if (testGroup) {
              operations.push(env.ARC_DATA.delete(`used_${testGroup}`));
            }
            
            // 2️⃣ 归档进度数据
            const progressKey = `progress_${sessionId}`;
            const progressJson = await env.ARC_DATA.get(progressKey);
            if (progressJson) {
              const archiveKey = `progress_archived_${sessionId}_auto_cleaned_${new Date().toISOString().replace(/[:.]/g, '')}`;
              operations.push(env.ARC_DATA.put(archiveKey, progressJson));
              operations.push(env.ARC_DATA.delete(progressKey));
            }
            
            // 3️⃣ 删除分配锁
            operations.push(env.ARC_DATA.delete(`assign_lock_${participant_id}`));
            
            // 4️⃣ 更新 assignment 状态为 'duplicate_cleaned'
            const assignmentKey = `assignment_${sessionId}`;
            const updatedAssignment = {
              ...duplicate.data,
              status: 'duplicate_cleaned',
              cleaned_at: new Date().toISOString(),
              kept_session_id: matchedAssignments[0].session_id,
              reason: `Auto-cleaned duplicate assignment, kept earliest (${matchedAssignments[0].session_id}, ${matchedAssignments[0].assigned_at})`
            };
            operations.push(env.ARC_DATA.put(assignmentKey, JSON.stringify(updatedAssignment)));
            
            // 5️⃣ 更新 session 状态
            const sessionKey = `session_${sessionId}`;
            const sessionJson = await env.ARC_DATA.get(sessionKey);
            if (sessionJson) {
              const session = JSON.parse(sessionJson);
              session.status = 'duplicate_cleaned';
              session.cleaned_at = new Date().toISOString();
              session.kept_session_id = matchedAssignments[0].session_id;
              operations.push(env.ARC_DATA.put(sessionKey, JSON.stringify(session)));
            }
            
            // 并行执行所有操作
            await Promise.all(operations);
          });
          
          // 等待所有清理操作完成
          await Promise.all(cleanupPromises);
          
          console.log(`✅ [AUTO-CLEANUP] Cleaned ${matchedAssignments.length - 1} duplicates for ${participant_id}, kept earliest ${matchedAssignments[0].session_id}`);
        }
      }
    }

    return new Response(JSON.stringify({ 
      success: true,
      has_saved_progress: hasSavedProgress,
      saved_data: savedProgressData,
      has_assigned_url: hasAssignedUrl,
      assigned_url: assignedUrlData
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      success: false,
      message: 'Failed to verify participant ID: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理参与者ID更新
async function handleUpdateParticipantId(request, corsHeaders, env) {
  try {
    const { sessionId, participantId } = await request.json();
    
    if (!sessionId || !participantId) {
      return new Response(JSON.stringify({ 
        error: 'Session ID and Participant ID are required' 
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 获取现有分配信息
    const assignmentKey = `assignment_${sessionId}`;
    const existingAssignment = await env.ARC_DATA.get(assignmentKey);
    
    if (!existingAssignment) {
      return new Response(JSON.stringify({ error: 'Assignment not found' }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 更新参与者ID
    const assignment = JSON.parse(existingAssignment);
    assignment.participant_id = participantId;
    assignment.participant_id_updated_at = new Date().toISOString();

    // 保存更新后的分配信息
    await env.ARC_DATA.put(assignmentKey, JSON.stringify(assignment));

    return new Response(JSON.stringify({ 
      success: true,
      message: 'Participant ID updated successfully'
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      error: 'Failed to update participant ID: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理URL分配生成 - 带原子性保存
async function handleAssignUrl(request, corsHeaders, env) {
  try {
    // 🔧 v2.4.3: 提取participant_id和nickname
    let participantInfo = null;
    try {
      if (request.method === 'POST') {
        const requestData = await request.json();
        if (requestData.participant_id || requestData.participantId) {
          participantInfo = {
            participant_id: requestData.participant_id || requestData.participantId,
            nickname: requestData.nickname || requestData.user_nickname || null
          };
          console.log(`[handleAssignUrl] Participant info:`, participantInfo);
        }
      }
    } catch (e) {
      console.warn(`[handleAssignUrl] Failed to parse request body:`, e);
    }
    
    // 🆕 v2.5.20: 检查该 participant_id 是否已有有效分配
    if (participantInfo?.participant_id) {
      console.log(`🔍 [handleAssignUrl] Checking existing assignments for participant: ${participantInfo.participant_id}`);
      
      const listResult = await env.ARC_DATA.list({ prefix: 'assignment_' });
      
      // 并行查询所有 assignment
      const assignmentPromises = listResult.keys.map(async (key) => {
        const assignment = await env.ARC_DATA.get(key.name);
        if (assignment) {
          const assignmentData = JSON.parse(assignment);
          // 检查是否是该用户的有效分配（assigned 或 completed 状态）
          if (assignmentData.participant_id === participantInfo.participant_id && 
              (assignmentData.status === 'assigned' || assignmentData.status === 'completed')) {
            return {
              session_id: key.name.replace('assignment_', ''),
              data: assignmentData
            };
          }
        }
        return null;
      });
      
      const results = await Promise.all(assignmentPromises);
      const existingAssignment = results.find(r => r !== null);
      
      // 如果找到已有分配，返回该分配而不是创建新的
      if (existingAssignment) {
        console.log(`✅ [handleAssignUrl] Found existing assignment for ${participantInfo.participant_id}: ${existingAssignment.session_id}`);
        console.log(`🔄 [handleAssignUrl] Returning existing assignment instead of creating new one`);
        
        return new Response(JSON.stringify({ 
          success: true,
          unique_url: existingAssignment.session_id,
          test_group: existingAssignment.data.test_group_file || existingAssignment.data.test_group,
          assignment_fingerprint: existingAssignment.data.assignment_fingerprint,
          assignment_sequence: existingAssignment.data.assignment_sequence || 1,
          reused: true,  // 标记为重用已有分配
          message: 'Reusing existing assignment for this participant'
        }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
      
      console.log(`➕ [handleAssignUrl] No existing assignment found, creating new one for ${participantInfo.participant_id}`);
    }
    
    // 生成唯一会话ID
    const sessionId = generateSessionId();
    
    // 🔧 移除分布式锁，使用简单的重试机制
    // KV 的最终一致性已经足够防止大多数冲突
    
    // 🔧 v2.4.3: 传递participantInfo到原子分配函数
    const assignment = await performAtomicAssignment(env, sessionId, participantInfo);
    
    if (!assignment) {
      return new Response(JSON.stringify({ 
        error: 'No available test groups' 
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 检查是否有错误（如 URL 已完成）
    if (assignment.error) {
      return new Response(JSON.stringify(assignment), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 成功分配，返回完整信息（包括 fingerprint）
    return new Response(JSON.stringify({ 
      success: true,
      unique_url: sessionId,
      test_group: assignment.test_group_file,
      assignment_fingerprint: assignment.assignment_fingerprint,  // 返回指纹给前端
      assignment_sequence: assignment.assignment_sequence,
      remaining_count: null  // 在Cloudflare 中计算剩余数量成本较高，可选实现
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({ 
      error: 'Failed to assign URL: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 生成 SHA256 指纹（JavaScript 实现）
async function generateFingerprint(url, timestamp) {
  const encoder = new TextEncoder();
  const data = encoder.encode(`${url}-${timestamp}`);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex.substring(0, 16);
}

// 获取 Assignment History
async function getAssignmentHistory(env, url) {
  const historyKey = `history_${url}`;
  const historyJson = await env.ARC_DATA.get(historyKey);
  return historyJson ? JSON.parse(historyJson) : [];
}

// 保存 Assignment History
async function saveAssignmentHistory(env, url, history) {
  const historyKey = `history_${url}`;
  await env.ARC_DATA.put(historyKey, JSON.stringify(history));
}

// 原子性分配执行（完全重写，包与Flask 所有功能）
async function performAtomicAssignment(env, sessionId, participantInfo = null) {
  console.log(`🔄 [performAtomicAssignment] START - Session ID: ${sessionId}`);
  
  // 获取可用的测试组
  const availableGroups = await getAvailableTestGroups(env);
  
  console.log(`📊 [performAtomicAssignment] Available groups count: ${availableGroups.length}`);
  
  if (availableGroups.length === 0) {
    console.error(`❌ [performAtomicAssignment] NO AVAILABLE GROUPS!`);
    return null;
  }

  // 随机选择一个可用的测试组（与Flask 保持一致）
  const testGroup = availableGroups[Math.floor(Math.random() * availableGroups.length)];
  
  // 检查URL 是否已存在分配记录
  const existingAssignmentJson = await env.ARC_DATA.get(`assignment_${sessionId}`);
  const existingAssignment = existingAssignmentJson ? JSON.parse(existingAssignmentJson) : null;
  
  // 获取锁URL 的历史记录
  let assignmentHistory = await getAssignmentHistory(env, sessionId);
  
  if (existingAssignment) {
    const currentStatus = existingAssignment.status;
    const isLocked = existingAssignment.locked || false;
    
    // 情况1：URL 已经成功完成且未被标记为再分配- 不允许重新分配
    if (currentStatus === 'completed' && !isLocked) {
      console.log(`🚫 URL ${sessionId} already completed, cannot reassign`);
      return {
        error: 'url_already_completed',
        message: '该URL已完成测试，不能重新分配',
        completed_at: existingAssignment.completed_at
      };
    }
    
    // 情况2：URL 已完成并被标记为"reassigned"状态（管理员手动再分配）
    if (currentStatus === 'reassigned') {
      console.log(`🔄 URL ${sessionId} was marked for reassignment, creating new assignment`);
      
      // 检查是否已经在历史中（避免重复）
      const lastHistory = assignmentHistory.length > 0 ? assignmentHistory[assignmentHistory.length - 1] : null;
      if (!lastHistory || lastHistory.status !== 'completed_then_reassigned') {
        // 添加到历史记录
        assignmentHistory.push({
          fingerprint: existingAssignment.assignment_fingerprint,
          test_group: existingAssignment.test_group_file,
          participant_id: existingAssignment.participant_id,
          assigned_at: existingAssignment.assigned_at,
          completed_at: existingAssignment.completed_at,
          reassigned_at: existingAssignment.reassigned_at,
          status: 'completed_then_reassigned'
        });
      }
    }
    
    // 情况3：URL 被锁定（可以重新分配）
    else if (isLocked) {
      console.log(`⚠️ URL ${sessionId} was locked, creating new assignment`);
      
      // 添加旧的锁定记录到历史
      assignmentHistory.push({
        fingerprint: existingAssignment.assignment_fingerprint,
        test_group: existingAssignment.test_group_file,
        participant_id: existingAssignment.participant_id,
        assigned_at: existingAssignment.assigned_at,
        locked_at: existingAssignment.attention_check_failed_at,
        status: 'locked',
        locked: true
      });
      
      // 将原测试组标记为可用（locked 的URL 释放测试组）
      await env.ARC_DATA.delete(`used_${existingAssignment.test_group_file}`);
    }
    
    // 情况4：URL 正在使用中且未锁定- 这不应该发生
    else if (currentStatus === 'assigned' && !isLocked) {
      console.log(`⚠️ WARNING: URL ${sessionId} is currently in use but not locked!`);
      
      // 保存到历史并继续
      assignmentHistory.push({
        fingerprint: existingAssignment.assignment_fingerprint,
        test_group: existingAssignment.test_group_file,
        participant_id: existingAssignment.participant_id,
        assigned_at: existingAssignment.assigned_at,
        status: 'replaced',
        locked: false,
        replaced_at: new Date().toISOString()
      });
    }
    
    // 保存更新后的历史记录
    await saveAssignmentHistory(env, sessionId, assignmentHistory);
  }
  
  // 生成分配时间戳和指纹
  const assignmentTimestamp = new Date().toISOString();
  const assignmentFingerprint = await generateFingerprint(sessionId, assignmentTimestamp);
  
  // 计算分配序列表
  const assignmentSequence = assignmentHistory.length + 1;
  
  // 创建新的分配记录
  const assignment = {
    session_id: sessionId,
    test_group_file: testGroup,
    participant_id: participantInfo?.participant_id || null,
    participant_info: participantInfo || {},
    assigned_at: assignmentTimestamp,
    assignment_fingerprint: assignmentFingerprint,  // 分配指纹，用于区分同一URL的不同分配
    status: 'assigned',
    access_count: 0,
    locked: false,  // 新分配默认不锁定
    completed_at: null,
    assignment_sequence: assignmentSequence  // 记录这是第几次分配
  };

  // 原子性操作：同时保存分配信息和标记使用状态
  await Promise.all([
    env.ARC_DATA.put(`assignment_${sessionId}`, JSON.stringify(assignment)),
    env.ARC_DATA.put(`used_${testGroup}`, 'true'),
    env.ARC_DATA.put(`session_${sessionId}`, JSON.stringify({
      created_at: assignmentTimestamp,
      test_group: testGroup,
      participant_id: participantInfo?.participant_id || null,  // 🔧 添加 participant_id
      status: 'active',
      fingerprint: assignmentFingerprint
    }))
  ]);

  const sequenceInfo = assignmentSequence > 1 ? ` (assignment #${assignmentSequence})` : '';
  console.log(`✓Assigned test group '${testGroup}' to URL: ${sessionId}${sequenceInfo} (fingerprint: ${assignmentFingerprint})`);

  return assignment;
}

// 分布式锁实现
async function acquireLock(env, lockKey, lockValue, timeout) {
  try {
    // 检查锁是否已存储
    const existingLock = await env.ARC_DATA.get(lockKey);
    
    if (existingLock) {
      const lockData = JSON.parse(existingLock);
      const now = Date.now();
      
      // 检查锁是否过期
      if (now - lockData.timestamp < timeout) {
        return false; // 锁仍然有效
      }
      // 锁已过期，可以获取
    }
    
    // 设置新锁
    const lockData = {
      value: lockValue,
      timestamp: Date.now()
    };
    
    // KV expirationTtl 最小值是 60 秒
    const ttlSeconds = Math.max(60, Math.ceil(timeout / 1000));
    
    await env.ARC_DATA.put(lockKey, JSON.stringify(lockData), {
      expirationTtl: ttlSeconds
    });
    
    return true;
    
  } catch (error) {
    console.error('Failed to acquire lock:', error);
    return false;
  }
}

// 释放分布式锁
async function releaseLock(env, lockKey, lockValue) {
  try {
    const existingLock = await env.ARC_DATA.get(lockKey);
    
    if (existingLock) {
      const lockData = JSON.parse(existingLock);
      
      // 只有锁的持有者才能释放锁
      if (lockData.value === lockValue) {
        await env.ARC_DATA.delete(lockKey);
      }
    }
    
  } catch (error) {
    console.error('Failed to release lock:', error);
  }
}

// 处理统计信息请求
async function handleGetStats(request, corsHeaders, env) {
  try {
    const stats = await calculateStats(env);
    
    return new Response(JSON.stringify({
      success: true,
      ...stats
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message,
      available_groups: 0,
      total_participants: 0,
      completion_rate: '0%',
      total_groups: 100
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 处理主页请求的 路由器
async function handleIndex(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const assignedGroup = url.searchParams.get('assigned_group');
    const sessionId = url.searchParams.get('session_id');
    
    // 如果有assigned_group 和session_id 参数，返回测试界面
    if (assignedGroup && sessionId) {
      return await handleTestInterface(request, corsHeaders, env);
    }
    
    // 否则返回欢迎页面
    // 尝试从KV 读取自定义欢迎页面
    const welcomeHtml = await env.ARC_DATA.get('static_welcome_html');
    
    if (welcomeHtml) {
      return new Response(welcomeHtml, {
        headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
      });
    }
    
    // 如果 KV 中没有，返回默认欢迎页面
    return new Response(getDefaultWelcomeHTML(), {
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
    
  } catch (error) {
    console.error('Error serving index:', error);
    return new Response(getDefaultWelcomeHTML(), {
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// 处理测试界面请求
async function handleTestInterface(request, corsHeaders, env) {
  try {
    // 尝试从KV 读取测试界面 HTML
    const testInterfaceHtml = await env.ARC_DATA.get('static_test_interface_html');
    
    if (testInterfaceHtml) {
      return new Response(testInterfaceHtml, {
        headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
      });
    }
    
    // 如果 KV 中没有，返回错误提示
    return new Response(getTestInterfaceNotFoundHTML(), {
      status: 404,
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
    
  } catch (error) {
    console.error('Error serving test interface:', error);
    return new Response(getTestInterfaceNotFoundHTML(), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// 处理 /test/<unique_url> 路径
async function handleTestUrl(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const uniqueUrl = url.pathname.replace('/test/', '');
    const participantId = url.searchParams.get('participant_id');
    
    if (!uniqueUrl) {
      return new Response('Invalid test URL', {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'text/plain' }
      });
    }
    
    // 获取分配信息
    const assignmentJson = await env.ARC_DATA.get(`assignment_${uniqueUrl}`);
    
    if (!assignmentJson) {
      return new Response(getInvalidTestLinkHTML(), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    const testGroup = assignment.test_group_file;
    const fingerprint = assignment.assignment_fingerprint || '';
    
    // 🔧 v2.4.0: 重定向到主页，传递测试组信息、分配指纹和participant_id
    let redirectUrl = `${url.origin}/?assigned_group=${testGroup}&session_id=${uniqueUrl}&assignment_fingerprint=${fingerprint}`;
    if (participantId) {
      redirectUrl += `&participant_id=${encodeURIComponent(participantId)}`;
    }
    
    return new Response(null, {
      status: 302,
      headers: {
        ...corsHeaders,
        'Location': redirectUrl
      }
    });
    
  } catch (error) {
    console.error('Error handling test URL:', error);
    return new Response(getInvalidTestLinkHTML(), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// 处理教程界面请求
async function handleTutorial(corsHeaders, env) {
  // 教程界面与测试界面相同
  return await handleTestInterface({ url: '' }, corsHeaders, env);
}

// 处理 consent_end 页面请求
async function handleConsentEnd(corsHeaders, env) {
  try {
    // 尝试从KV 中读取consent_end.html
    const consentEndHtml = await env.ARC_DATA.get('static_consent_end_html');
    
    if (consentEndHtml) {
      return new Response(consentEndHtml, {
        headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
      });
    }
    
    // 如果 KV 中没有，返回默认的感谢页面
    return new Response(getDefaultConsentEndHTML(), {
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
    
  } catch (error) {
    console.error('Error serving consent_end:', error);
    return new Response(getDefaultConsentEndHTML(), {
      headers: { ...corsHeaders, 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// 处理自动分配开始请求
async function handleAutoAssignStart(request, corsHeaders, env) {
  let participantId = '';  // 🔧 v2.5.15: 在函数作用域声明，避免 catch 块中 undefined
  
  try {
    const url = new URL(request.url);
    participantId = url.searchParams.get('participant_id');
    
    console.log(`🚀 [handleAutoAssignStart] START - Participant ID: ${participantId}`);
    console.log(`🚀 [handleAutoAssignStart] Request URL: ${request.url}`);
    
    // 🆕 v2.5.10: 防止并发请求 - 检查是否有进行中的分配请求
    if (participantId) {
      const lockKey = `assign_lock_${participantId}`;
      const existingLock = await env.ARC_DATA.get(lockKey);
      
      if (existingLock) {
        const lockData = JSON.parse(existingLock);
        const lockAge = Date.now() - new Date(lockData.created_at).getTime();
        
        // 如果锁未过期（5秒内），返回已有的 session_id
        if (lockAge < 5000) {
          console.log(`🔒 [handleAutoAssignStart] Duplicate request detected for ${participantId}, lock age: ${lockAge}ms`);
          
          // 🔧 v2.5.15: 如果是 pending 状态的锁（分配还在进行中），告诉前端稍等
          if (lockData.status === 'pending') {
            console.log(`⏳ [handleAutoAssignStart] Assignment is still in progress, ask client to retry`);
            return new Response(null, {
              status: 302,
              headers: {
                ...corsHeaders,
                'Location': `/?error=assignment_in_progress&participant_id=${encodeURIComponent(participantId)}&retry=true`
              }
            });
          }
          
          // 如果已经分配完成，返回已有的 session_id
          if (lockData.session_id) {
            console.log(`✅ [handleAutoAssignStart] Returning existing session: ${lockData.session_id}`);
            
            const testGroup = lockData.test_group || '';
            const testGroupName = testGroup.replace('.json', '');
            
            const params = new URLSearchParams({
              session_id: lockData.session_id,
              assigned_group: testGroupName,
              assignment_fingerprint: lockData.assignment_fingerprint || ''
            });
            
            if (participantId) {
              params.set('participant_id', participantId);
            }
            
            const redirectUrl = `/app?${params.toString()}`;
            
            return new Response(null, {
              status: 302,
              headers: {
                ...corsHeaders,
                'Location': redirectUrl
              }
            });
          }
        }
      }
      
      // 🆕 v2.5.15: 创建一个 pending 锁（表示正在分配中）
      const pendingLock = {
        status: 'pending',
        participant_id: participantId,
        created_at: new Date().toISOString()
      };
      
      await env.ARC_DATA.put(lockKey, JSON.stringify(pendingLock), {
        expirationTtl: 10  // 10 秒后自动过期
      });
      
      console.log(`🔐 [handleAutoAssignStart] Created pending lock for ${participantId}`);
    }
    
    // �🔧 v2.4.3: 创建POST请求并传递participant_id
    const assignRequest = new Request(request.url, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        participant_id: participantId
      })
    });
    
    // 自动分配一个测试组
    console.log(`📋 [handleAutoAssignStart] Calling handleAssignUrl...`);
    const assignment = await handleAssignUrl(
      assignRequest, 
      corsHeaders, 
      env
    );
    
    console.log(`📋 [handleAutoAssignStart] handleAssignUrl returned, status: ${assignment.status}`);
    
    // 🔧 v2.5.15: 添加详细的错误日志
    let assignmentData;
    try {
      assignmentData = await assignment.json();
      console.log(`✅ [handleAutoAssignStart] Assignment response:`, JSON.stringify(assignmentData).substring(0, 200));
      
      // 🔧 v2.5.15: 检查返回的数据是否包含错误
      if (assignmentData.error) {
        console.error(`❌ [handleAutoAssignStart] Assignment returned error:`, assignmentData.error);
        throw new Error(`Assignment failed: ${assignmentData.error}`);
      }
      
    } catch (jsonError) {
      console.error(`❌ [handleAutoAssignStart] Failed to parse assignment response:`, jsonError);
      console.error(`❌ Response status: ${assignment.status}, statusText: ${assignment.statusText}`);
      
      // 尝试读取原始响应文本
      try {
        const clonedResponse = assignment.clone();
        const rawText = await clonedResponse.text();
        console.error(`Raw response text: ${rawText.substring(0, 500)}`);
      } catch (e) {
        console.error(`Cannot read response text:`, e);
      }
      
      throw new Error(`Failed to parse assignment response: ${jsonError.message}`);
    }
    
    // 🆕 v2.5.10: 分配成功后，更新锁状态为 completed
    if (assignmentData.success && participantId) {
      const lockKey = `assign_lock_${participantId}`;
      const lockData = {
        status: 'completed',  // 🔧 v2.5.15: 标记为已完成
        session_id: assignmentData.unique_url,
        test_group: assignmentData.test_group || assignmentData.test_group_file,
        assignment_fingerprint: assignmentData.assignment_fingerprint,
        created_at: new Date().toISOString()
      };
      
      // 设置 5 秒 TTL
      await env.ARC_DATA.put(lockKey, JSON.stringify(lockData), {
        expirationTtl: 5
      });
      
      console.log(`✅ [handleAutoAssignStart] Updated lock to completed for ${participantId}`);
    }
    
    if (assignmentData.success) {
      // 🔧 修复: 重定向到 /app，同时传递 assignedGroup 参数（兼容原有逻辑）
      const testGroup = assignmentData.test_group || assignmentData.test_group_file;
      const testGroupName = testGroup ? testGroup.replace('.json', '') : '';
      
      const params = new URLSearchParams({
        session_id: assignmentData.unique_url,
        assigned_group: testGroupName,  // ← 添加这个参数！
        assignment_fingerprint: assignmentData.assignment_fingerprint || ''
      });
      
      // 添加 participant_id（如果有）
      if (participantId) {
        params.set('participant_id', participantId);
      }
      
      const redirectUrl = `/app?${params.toString()}`;
      
      console.log(`[/start] Redirecting to: ${redirectUrl}`);
      console.log(`[/start] Assigned group: ${testGroupName}`);
      
      return new Response(null, {
        status: 302,
        headers: {
          ...corsHeaders,
          'Location': redirectUrl
        }
      });
    } else {
      // 分配失败，重定向到首页并显示错误
      return new Response(null, {
        status: 302,
        headers: {
          ...corsHeaders,
          'Location': '/?error=no_groups_available'
        }
      });
    }

  } catch (error) {
    console.error('❌❌❌ [/start] CRITICAL ERROR ❌❌❌');
    console.error('[/start] Error message:', error.message);
    console.error('[/start] Error stack:', error.stack);
    console.error('[/start] Participant ID:', participantId);
    console.error('[/start] Error type:', error.constructor.name);
    console.error('[/start] Full error object:', JSON.stringify(error, Object.getOwnPropertyNames(error)));
    
    // 🔧 v2.5.15: 根据错误类型返回不同的错误信息
    let errorType = 'assignment_error';
    if (error.message && error.message.includes('parse')) {
      errorType = 'parse_error';
      console.error('[/start] Detected as PARSE ERROR');
    } else if (error.message && error.message.includes('timeout')) {
      errorType = 'timeout_error';
      console.error('[/start] Detected as TIMEOUT ERROR');
    } else if (error.message && error.message.includes('available')) {
      errorType = 'no_groups_available';
      console.error('[/start] Detected as NO GROUPS AVAILABLE');
    }
    
    console.error(`[/start] Redirecting to /?error=${errorType}&participant_id=${participantId || '(empty)'}`);
    
    // 错误时重定向到首页
    return new Response(null, {
      status: 302,
      headers: {
        ...corsHeaders,
        'Location': `/?error=${errorType}&participant_id=${encodeURIComponent(participantId || '')}`
      }
    });
  }
}

// 计算统计信息（包含locked 的reassigned 状态处理）
// 🔧 优化后的版本：简化逻辑，提升性能
async function calculateStats(env) {
  let totalAssigned = 0;
  let totalCompleted = 0;
  let totalInProgress = 0;
  let totalAttentionCheckFailed = 0;
  let totalTimeoutLocked = 0;
  let totalDuplicateCleaned = 0;
  let totalReassigned = 0;
  
  // 🔧 v2.5.9: 从 assignment_ 前缀统计所有状态
  const assignmentKeys = await env.ARC_DATA.list({ prefix: 'assignment_' });
  
  for (const key of assignmentKeys.keys) {
    const assignmentJson = await env.ARC_DATA.get(key.name);
    if (assignmentJson) {
      try {
        const assignment = JSON.parse(assignmentJson);
        totalAssigned++;
        
        // 根据状态统计
        if (assignment.status === 'completed') {
          totalCompleted++;
        } else if (assignment.status === 'attention_check_failed') {
          totalAttentionCheckFailed++;
        } else if (assignment.status === 'timeout_locked') {
          totalTimeoutLocked++;
        } else if (assignment.status === 'duplicate_cleaned') {
          totalDuplicateCleaned++;
        } else if (assignment.status === 'reassigned') {
          totalReassigned++;
        } else if (assignment.status === 'assigned') {
          totalInProgress++;
        }
      } catch (parseError) {
        console.error(`Failed to parse assignment ${key.name}:`, parseError);
      }
    }
  }
  
  // 🔧 使用 getAvailableTestGroups 来获取可用测试组数量
  const availableTestGroups = await getAvailableTestGroups(env);
  const availableGroups = availableTestGroups.length;
  
  const completionRate = totalAssigned > 0 ? (totalCompleted / totalAssigned * 100).toFixed(1) : 0;
  
  return {
    available_groups: availableGroups,
    total_assigned: totalAssigned,
    total_completed: totalCompleted,
    in_progress: totalInProgress,
    attention_check_failed: totalAttentionCheckFailed,
    timeout_locked: totalTimeoutLocked,
    duplicate_cleaned: totalDuplicateCleaned,
    reassigned: totalReassigned,
    completion_rate: `${completionRate}%`,
    total_groups: 100
  };
}

// 生成无可用组的HTML页面
function getNoGroupsAvailableHTML() {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC测试 - 暂无可用测试组/title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 40px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 500px;
        }
        h1 { font-size: 2.5em; margin-bottom: 20px; }
        p { font-size: 1.2em; line-height: 1.6; margin-bottom: 30px; }
        .icon { font-size: 4em; margin-bottom: 20px; }
        .btn { 
            background: rgba(255,255,255,0.2); 
            color: white; 
            padding: 15px 30px; 
            border: 2px solid white; 
            border-radius: 10px; 
            font-size: 1.1em; 
            text-decoration: none; 
            display: inline-block;
            transition: all 0.3s;
        }
        .btn:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📋</div>
        <h1>暂无可用测试组/h1>
        <p>很抱歉，目前所有测试组都已被分配完毕。/p>
        <p>请稍后再试或联系管理员获取更多信息。/p>
        <a href="/" class="btn">返回主页</a>
    </div>
</body>
</html>`;
}

// 生成分配错误的HTML页面
function getAssignmentErrorHTML(errorMessage) {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC测试 - 分配错误</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 40px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 500px;
        }
        h1 { font-size: 2.5em; margin-bottom: 20px; }
        p { font-size: 1.2em; line-height: 1.6; margin-bottom: 30px; }
        .icon { font-size: 4em; margin-bottom: 20px; }
        .error { 
            background: rgba(255,255,255,0.1); 
            padding: 15px; 
            border-radius: 10px; 
            font-family: monospace; 
            margin: 20px 0; 
        }
        .btn { 
            background: rgba(255,255,255,0.2); 
            color: white; 
            padding: 15px 30px; 
            border: 2px solid white; 
            border-radius: 10px; 
            font-size: 1.1em; 
            text-decoration: none; 
            display: inline-block;
            transition: all 0.3s;
            margin: 5px;
        }
        .btn:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">⚠️</div>
        <h1>分配失败</h1>
        <p>在自动分配测试组时发生了错误。/p>
        <div class="error">错误信息: ${errorMessage}</div>
        <p>请刷新页面重试或联系管理员。/p>
        <a href="/start" class="btn">重新尝试</a>
        <a href="/" class="btn">返回主页</a>
    </div>
</body>
</html>`;
}

// 生成默认的consent_end 感谢页面
function getDefaultConsentEndHTML() {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC测试 - 感谢参与</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 40px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 600px;
        }
        h1 { 
            font-size: 2.5em; 
            margin-bottom: 20px; 
        }
        p { 
            font-size: 1.2em; 
            line-height: 1.6; 
            margin-bottom: 20px; 
        }
        .icon { 
            font-size: 5em; 
            margin-bottom: 20px; 
        }
        .message { 
            background: rgba(255,255,255,0.1); 
            padding: 20px; 
            border-radius: 10px; 
            margin: 20px 0; 
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🎉</div>
        <h1>感谢您的参与！/h1>
        <div class="message">
            <p>您已成功完成ARC测试组/p>
            <p>您的回答已被记录，非常感谢您的时间和努力。/p>
        </div>
        <p>如有任何问题，请联系研究团队。/p>
    </div>
</body>
</html>`;
}

// 生成默认欢迎页面
function getDefaultWelcomeHTML() {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC Challenge - Welcome</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 50px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 700px;
        }
        h1 { 
            font-size: 3em; 
            margin-bottom: 20px; 
        }
        p { 
            font-size: 1.3em; 
            line-height: 1.8; 
            margin-bottom: 30px; 
        }
        .icon { 
            font-size: 5em; 
            margin-bottom: 20px; 
        }
        .btn { 
            background: rgba(255,255,255,0.3); 
            color: white; 
            padding: 20px 40px; 
            border: 2px solid white; 
            border-radius: 10px; 
            font-size: 1.3em; 
            text-decoration: none; 
            display: inline-block;
            transition: all 0.3s;
            margin: 10px;
        }
        .btn:hover { 
            background: rgba(255,255,255,0.5); 
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🧩</div>
        <h1>欢迎参加 ARC Challenge</h1>
        <p>欢迎来到抽象推理挑战测试平台。/p>
        <p>点击下方按钮开始您的测试之旅。/p>
        <a href="/start" class="btn">开始测试/a>
    </div>
</body>
</html>`;
}

// 生成测试界面未找到页面
function getTestInterfaceNotFoundHTML() {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC Challenge - Interface Not Found</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 40px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 600px;
        }
        h1 { font-size: 2.5em; margin-bottom: 20px; }
        p { font-size: 1.2em; line-height: 1.6; margin-bottom: 20px; }
        .icon { font-size: 4em; margin-bottom: 20px; }
        .btn { 
            background: rgba(255,255,255,0.2); 
            color: white; 
            padding: 15px 30px; 
            border: 2px solid white; 
            border-radius: 10px; 
            font-size: 1.1em; 
            text-decoration: none; 
            display: inline-block;
            transition: all 0.3s;
        }
        .btn:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">⚠️</div>
        <h1>测试界面未配置/h1>
        <p>测试界面HTML文件尚未上传到系统。/p>
        <p>请联系管理员上传 arc_grid_editor.html 文件从KV 存储）/p>
        <p><code>wrangler kv:key put --binding=ARC_DATA "static_test_interface_html" --path=./arc_grid_editor.html</code></p>
        <a href="/" class="btn">返回主页</a>
    </div>
</body>
</html>`;
}

// 生成无效测试链接页面
function getInvalidTestLinkHTML() {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ARC Challenge - Invalid Link</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { 
            background: rgba(255,255,255,0.1); 
            padding: 40px; 
            border-radius: 20px; 
            backdrop-filter: blur(10px);
            max-width: 600px;
        }
        h1 { font-size: 2.5em; margin-bottom: 20px; }
        p { font-size: 1.2em; line-height: 1.6; margin-bottom: 20px; }
        .icon { font-size: 4em; margin-bottom: 20px; }
        .btn { 
            background: rgba(255,255,255,0.2); 
            color: white; 
            padding: 15px 30px; 
            border: 2px solid white; 
            border-radius: 10px; 
            font-size: 1.1em; 
            text-decoration: none; 
            display: inline-block;
            transition: all 0.3s;
        }
        .btn:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">⚠/div>
        <h1>无效的测试链接/h1>
        <p>抱歉，您访问的测试链接无效或已过期。/p>
        <p>请联系实验管理员获取有效的测试链接。/p>
        <a href="/" class="btn">返回主页</a>
    </div>
</body>
</html>`;
}

// 工具函数：生成会话ID
function generateSessionId() {
  const chars = '0123456789abcdef';
  let result = '';
  for (let i = 0; i < 16; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

// ============================================
// 进度保存与加载功能(v2.4.0)
// ============================================

/**
 * 保存测试进度到KV存储
 * 键名格式: progress_{user_nickname 和session_id}
 */
async function handleSaveProgress(request, corsHeaders, env) {
  try {
    const data = await request.json();
    const sessionId = data.session_id || data.sessionId;
    const userNickname = data.user_nickname || data.userNickname;
    
    if (!sessionId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'Session ID is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 验证URL是否有效
    const assignmentJson = await env.ARC_DATA.get(`assignment_${sessionId}`);
    if (!assignmentJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'Invalid session ID'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    
    // 🕐 首先检查URL是否超时（48小时限制）
    const timeoutCheck = checkUrlTimeout(assignment);
    if (timeoutCheck.is_timeout) {
      console.log(`⏰ Session ${sessionId} has timed out - rejecting save progress`);
      
      // 如果还未标记为超时，现在标记
      if (assignment.status !== 'timeout_locked') {
        assignment.status = 'timeout_locked';
        assignment.timeout_at = new Date().toISOString();
        await env.ARC_DATA.put(`assignment_${sessionId}`, JSON.stringify(assignment));
        
        // 归档进度文件
        await archiveSavedProgress(env, sessionId, userNickname || assignment.participant_id, 'timeout');
      }
      
      return new Response(JSON.stringify({ 
        success: false,
        error: 'assignment_timeout',
        message: '您的测试已超时（超过48小时限制），不允许保存进度',
        timeout_at: timeoutCheck.timeout_at,
        status: 'timeout_locked'
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 🔧 检查是否被锁定（attention check失败）
    if (assignment.locked || assignment.status === 'attention_check_failed') {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'assignment_locked',
        message: '该测试已被锁定（Attention Check失败），不允许保存进度',
        failed_at: assignment.attention_check_failed_at,
        assignment_fingerprint: assignment.assignment_fingerprint
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 检查是否已完成
    if (assignment.status === 'completed') {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'already_completed',
        message: '测试已经完成，不允许保存进度',
        completed_at: assignment.completed_at
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 确定保存键名：优先使用user_nickname
    const saveKey = userNickname || sessionId;
    const kvKey = `progress_${saveKey}`;
    
    // 获取 session 创建时间（作为真正的测试开始时间）
    let testStartTime = null;
    if (data.timing && data.timing.testStartTime) {
      testStartTime = data.timing.testStartTime;
    } else {
      // 如果前端没有提供 testStartTime，从 session KV 中获取 created_at
      const sessionKey = `session_${sessionId}`;
      const sessionData = await env.ARC_DATA.get(sessionKey);
      if (sessionData) {
        const session = JSON.parse(sessionData);
        testStartTime = session.created_at;
        console.log(`Using session created_at as testStartTime: ${testStartTime}`);
      }
    }
    
    // 准备进度数据 - 保存完整的数据结构
    const progressData = {
      // 基本信息
      session_id: sessionId,
      user_nickname: userNickname || '',
      test_group: data.test_group || assignment.test_group_file,
      participant_id: data.participant_id || userNickname || sessionId,
      assignment_fingerprint: assignment.assignment_fingerprint,
      
      // 进度状态
      isMultipleProblem: data.isMultipleProblem || false,
      totalProblems: data.totalProblems || 0,
      currentProblem: data.currentProblem || 1,
      totalTests: data.totalTests || 0,
      currentTest: data.currentTest || 1,
      currentProblemIndex: data.currentProblemIndex || 0,
      
      // 问题名称
      problemNames: data.problemNames || {},
      
      // 答案历史 (对象格式，键为 "problemIndex_testIndex")
      problemAnswers: data.problemAnswers || {},
      
      // 当前答案
      currentAnswer: data.currentAnswer || {
        answer: [],
        rows: 0,
        cols: 0,
        problemIndex: 0,
        testIndex: 0
      },
      
      // 问题描述 (对象格式，键为 problemIndex)
      target: data.target || {},
      
      // 🆕 难度评分 (对象格式，键为 problemIndex，值为 {thinking: "easy", drawing: "medium"})
      difficultyRatings: data.difficultyRatings || {},
      
      // 🆕 编辑模式教程跟踪
      hasSeenEditTutorial: data.hasSeenEditTutorial || false,
      
      // 计时信息（使用 session created_at 作为 testStartTime 的后备）
      timing: {
        totalTimeMs: data.timing?.totalTimeMs || 0,
        totalTimeFormatted: data.timing?.totalTimeFormatted || '00:00:00',
        timePerProblemMs: data.timing?.timePerProblemMs || {},
        timePerProblemFormatted: data.timing?.timePerProblemFormatted || {},
        testStartTime: testStartTime,  // 优先使用前端提供的，否则使用 session created_at
        saveTime: new Date().toISOString()
      },
      
      // 保存时间
      lastSaveTime: new Date().toISOString()
    };
    
    // 🔍 调试日志：检查 difficultyRatings 是否被保存
    console.log('💾 Saving progress:', {
      kvKey,
      sessionId,
      userNickname,
      hasDifficultyRatings: !!data.difficultyRatings,
      difficultyRatingsKeys: data.difficultyRatings ? Object.keys(data.difficultyRatings) : []
    });
    
    // 保存到KV存储
    await env.ARC_DATA.put(kvKey, JSON.stringify(progressData));
    
    console.log(`Progress saved for ${saveKey} (session: ${sessionId})`);
    
    return new Response(JSON.stringify({ 
      success: true,
      message: 'Progress saved successfully',
      save_key: saveKey,
      save_time: progressData.lastSaveTime
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('Save progress error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to save progress: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

/**
 * 加载已保存的进度
 * 查询参数: session_id (必需), user_nickname (可用
 */
async function handleLoadProgress(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    let sessionId, userNickname, participantId;
    
    // 支持两种方式：GET (URL params) 和 POST (body)
    if (request.method === 'POST') {
      const body = await request.json();
      sessionId = body.session_id || url.searchParams.get('session_id');
      userNickname = body.user_nickname || url.searchParams.get('user_nickname');
      participantId = body.participant_id;
    } else {
      sessionId = url.searchParams.get('session_id');
      userNickname = url.searchParams.get('user_nickname');
      participantId = url.searchParams.get('participant_id');
    }
    
    // 确定加载键名：优先使用 participant_id, 然后 user_nickname, 最后 session_id
    const loadKey = participantId || userNickname || sessionId;
    
    if (!loadKey) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'participant_id, user_nickname, or session_id is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const kvKey = `progress_${loadKey}`;
    
    // 从KV存储加载进度
    const progressJson = await env.ARC_DATA.get(kvKey);
    
    if (!progressJson) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'No saved progress found'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const progressData = JSON.parse(progressJson);
    
    // 如果提供了 session_id，验证匹配
    if (sessionId && progressData.session_id && progressData.session_id !== sessionId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'Session ID mismatch'
      }), {
        status: 403,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    console.log(`Progress loaded for ${loadKey}` + (sessionId ? ` (session: ${sessionId})` : ''));
    
    return new Response(JSON.stringify({ 
      success: true,
      progress_data: progressData  // 注意字段名改为 progress_data，与前端一致
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('Load progress error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Failed to load progress: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

/**
 * 检查是否有已保存的进度
 * 查询参数: session_id (必需), user_nickname (可用
 */
async function handleCheckSavedProgress(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    let sessionId, userNickname, participantId;
    
    // 支持 GET 和 POST 两种方式
    if (request.method === 'POST') {
      const body = await request.json();
      sessionId = body.session_id || url.searchParams.get('session_id');
      userNickname = body.user_nickname || url.searchParams.get('user_nickname');
      participantId = body.participant_id || url.searchParams.get('participant_id');
    } else {
      sessionId = url.searchParams.get('session_id');
      userNickname = url.searchParams.get('user_nickname');
      participantId = url.searchParams.get('participant_id');
    }
    
    if (!sessionId && !participantId) {
      return new Response(JSON.stringify({ 
        success: false,
        error: 'Session ID or Participant ID is required'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 确定检查键名：优先使用 user_nickname，其次 participantId，最后 sessionId
    const checkKey = userNickname || participantId || sessionId;
    const kvKey = `progress_${checkKey}`;
    
    console.log(`[handleCheckSavedProgress] Checking KV key: ${kvKey}`);
    
    // 检查KV存储中是否存在进度
    const progressJson = await env.ARC_DATA.get(kvKey);
    
    if (!progressJson) {
      console.log(`[handleCheckSavedProgress] No saved progress found for key: ${kvKey}`);
      return new Response(JSON.stringify({ 
        has_saved_progress: false
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const progressData = JSON.parse(progressJson);
    
    // 验证session_id匹配（如果提供了sessionId）
    if (sessionId && progressData.session_id && progressData.session_id !== sessionId) {
      console.log(`[handleCheckSavedProgress] Session ID mismatch: expected ${sessionId}, got ${progressData.session_id}`);
      return new Response(JSON.stringify({ 
        has_saved_progress: false,
        error: 'Session ID mismatch'
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 计算已完成的题目数量（problemAnswers 是对象，键为 "problemIndex_testIndex"）
    let answersCount = 0;
    if (progressData.problemAnswers && typeof progressData.problemAnswers === 'object') {
      answersCount = Object.keys(progressData.problemAnswers).length;
    }
    
    // 获取测试开始时间（优先从 timing 获取，否则从 session 获取）
    let testStartTime = progressData.timing?.testStartTime;
    if (!testStartTime && sessionId) {
      const sessionKey = `session_${sessionId}`;
      const sessionData = await env.ARC_DATA.get(sessionKey);
      if (sessionData) {
        const session = JSON.parse(sessionData);
        testStartTime = session.created_at;
      }
    }
    
    return new Response(JSON.stringify({ 
      has_saved_progress: true,
      saved_at: progressData.lastSaveTime || progressData.timing?.saveTime,  // 保存时间
      test_start_time: testStartTime,  // 测试开始时间
      session_id: progressData.session_id,
      test_group: progressData.test_group,
      problems_completed: answersCount,  // 已完成题目数
      current_problem: progressData.currentProblem || (progressData.currentProblemIndex + 1),  // 当前题目
      total_problems: progressData.totalProblems || 0
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('Check saved progress error:', error);
    return new Response(JSON.stringify({ 
      has_saved_progress: false,
      error: 'Failed to check progress: ' + error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

/**
 * 归档已保存的进度文件
 * @param {Object} env - Cloudflare环境对象
 * @param {string} sessionId - 会话ID
 * @param {string} userNickname - 用户昵称
 * @param {string} reason - 归档原因: 'submitted', 'timeout', 'attention_check_failed'
 */
async function archiveSavedProgress(env, sessionId, userNickname, reason) {
  try {
    if (!sessionId) {
      console.log('No session ID provided for archiving progress');
      return;
    }
    
    // 确定进度文件的键名
    const progressKey = userNickname || sessionId;
    const kvKey = `progress_${progressKey}`;
    
    // 检查是否有进度文件
    const progressJson = await env.ARC_DATA.get(kvKey);
    if (!progressJson) {
      console.log(`No progress file found for ${progressKey}, nothing to archive`);
      return;
    }
    
    // 获取当前日期（格式：YYYYMMDD）
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0].replace(/-/g, '');
    
    // 生成归档文件名
    let archiveKey;
    if (reason === 'submitted') {
      archiveKey = `progress_archived_${progressKey}_submitted_${dateStr}`;
    } else if (reason === 'timeout') {
      archiveKey = `progress_archived_${progressKey}_timeout_${dateStr}`;
    } else if (reason === 'attention_check_failed') {
      archiveKey = `progress_archived_${progressKey}_attention_check_failed_${dateStr}`;
    } else {
      archiveKey = `progress_archived_${progressKey}_${reason}_${dateStr}`;
    }
    
    // 保存归档副本
    await env.ARC_DATA.put(archiveKey, progressJson);
    
    // 删除原始进度文件
    await env.ARC_DATA.delete(kvKey);
    
    console.log(`✓Progress archived: ${kvKey} -> ${archiveKey} (reason: ${reason})`);
    
  } catch (error) {
    console.error('Archive progress error:', error);
    // 归档失败不应影响主流程，只记录错误
  }
}

// 工具函数：获取可用的测试组
// 🔧 优化后的版本：简化逻辑，提升性能
// locked 的reassigned 状态的测试组已在相应处理函数中删除 used_ 标记
async function getAvailableTestGroups(env) {
  console.log(`🔍 [getAvailableTestGroups] START - Checking 200 test groups...`);
  
  // 🆕 v2.5.17: 首先检查 R2 Bucket 中实际存在哪些测试组文件
  let existingFiles = [];
  
  if (!env.ARC_BUCKET) {
    console.error(`❌ [getAvailableTestGroups] ARC_BUCKET not configured!`);
    // 如果 R2 未配置，回退到假设所有文件都存在
    for (let i = 1; i <= 200; i++) {
      existingFiles.push(`test_group${i}.json`);
    }
  } else {
    try {
      // 列出 R2 Bucket 中 test/ 目录下的所有文件
      const listed = await env.ARC_BUCKET.list({ prefix: 'test/' });
      existingFiles = listed.objects
        .map(obj => obj.key.replace('test/', ''))
        .filter(name => name.match(/^test_group\d+\.json$/));
      
      console.log(`📁 [getAvailableTestGroups] Found ${existingFiles.length} test files in R2 Bucket`);
      
      if (existingFiles.length === 0) {
        console.error(`❌ [getAvailableTestGroups] NO TEST FILES IN R2 BUCKET!`);
        console.error(`❌ Please upload test_group1.json to test_group200.json to R2 Bucket`);
        return [];
      }
    } catch (r2Error) {
      console.error(`❌ [getAvailableTestGroups] Failed to list R2 Bucket:`, r2Error.message);
      // R2 访问失败，回退到假设所有文件都存在
      for (let i = 1; i <= 200; i++) {
        existingFiles.push(`test_group${i}.json`);
      }
    }
  }
  
  const allGroups = [];
  
  // 🚀 v2.5.19: 批量并行查询所有测试组的使用状态（优化性能）
  console.log(`🚀 [getAvailableTestGroups] Starting parallel check for ${existingFiles.length} files...`);
  
  const checkPromises = existingFiles.map(async (groupName) => {
    const used = await env.ARC_DATA.get(`used_${groupName}`);
    return { groupName, used };
  });
  
  const results = await Promise.all(checkPromises);
  
  // 筛选出未被使用的测试组
  const availableGroups = results
    .filter(result => !result.used)
    .map(result => result.groupName);
  
  allGroups.push(...availableGroups);
  
  console.log(`✅ [getAvailableTestGroups] Found ${allGroups.length} available groups (out of ${existingFiles.length} existing files)`);
  if (allGroups.length === 0) {
    console.error(`❌ [getAvailableTestGroups] ALL ${existingFiles.length} GROUPS ARE USED!`);
  } else if (allGroups.length < 10) {
    console.warn(`⚠️ [getAvailableTestGroups] Only ${allGroups.length} groups left!`);
    console.log(`Available groups:`, allGroups.slice(0, 5));
  }
  
  return allGroups;
}

// =============================================================================
// Admin API Functions (v2.5.0)
// =============================================================================

// Basic Auth 认证检查
function checkBasicAuth(request, env) {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader) {
    return false;
  }
  
  const [scheme, credentials] = authHeader.split(' ');
  if (scheme !== 'Basic') {
    return false;
  }
  
  try {
    const decoded = atob(credentials);
    const [username, password] = decoded.split(':');
    
    // 从环境变量获取管理员密码
    const adminPassword = env.ADMIN_PASSWORD || 'admin123';
    const adminUsername = env.ADMIN_USERNAME || 'admin';
    
    return username === adminUsername && password === adminPassword;
  } catch (error) {
    console.error('Auth decode error:', error);
    return false;
  }
}

// 获取统计数据
async function handleAdminStats(request, corsHeaders, env) {
  try {
    const stats = await calculateStats(env);
    
    return new Response(JSON.stringify(stats), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Get admin stats error:', error);
    return new Response(JSON.stringify({
      error: 'Failed to get statistics',
      message: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 获取分配列表(分页)
async function handleAdminAssignments(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const page = parseInt(url.searchParams.get('page') || '1');
    const perPage = parseInt(url.searchParams.get('per_page') || '20');
    
    // 🔧 v2.5.4: 从 assignment_ 前缀获取所有已分配的 assignment
    const allAssignments = [];
    const assignmentKeys = await env.ARC_DATA.list({ prefix: 'assignment_' });
    
    for (const key of assignmentKeys.keys) {
      const assignmentJson = await env.ARC_DATA.get(key.name);
      if (assignmentJson) {
        try {
          const assignment = JSON.parse(assignmentJson);
          const sessionId = key.name.replace('assignment_', '');
          
          allAssignments.push({
            session_id: sessionId,
            test_group: assignment.test_group_file || assignment.test_group,
            participant_id: assignment.participant_id || null,
            fingerprint: assignment.assignment_fingerprint || assignment.fingerprint,
            created_at: assignment.assigned_at || assignment.created_at,
            status: assignment.status || 'assigned',
            failed_at: assignment.failed_at || null,
            completed_at: assignment.completed_at || null,
            timeout_at: assignment.timeout_at || null,
            cleaned_at: assignment.cleaned_at || null,
            reassigned_at: assignment.reassigned_at || null,
            kept_session_id: assignment.kept_session_id || null,
            accuracy: assignment.accuracy || null,
            correct_answer: assignment.correct_answer || null,
            total_questions: assignment.total_questions || null
          });
        } catch (parseError) {
          console.error(`Failed to parse assignment ${key.name}:`, parseError);
        }
      }
    }
    
    // 按创建时间倒序排序
    allAssignments.sort((a, b) => {
      const dateA = new Date(a.created_at || 0);
      const dateB = new Date(b.created_at || 0);
      return dateB.getTime() - dateA.getTime();
    });
    
    // 分页
    const total = allAssignments.length;
    const totalPages = Math.ceil(total / perPage);
    const start = (page - 1) * perPage;
    const end = start + perPage;
    const assignments = allAssignments.slice(start, end);
    
    return new Response(JSON.stringify({
      assignments,
      pagination: {
        page,
        per_page: perPage,
        total,
        total_pages: totalPages,
        has_prev: page > 1,
        has_next: page < totalPages,
        prev_num: page - 1,
        next_num: page + 1
      }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Get admin assignments error:', error);
    return new Response(JSON.stringify({
      error: 'Failed to get assignments',
      message: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 🆕 v2.5.9: Admin手动清理超时分配
async function handleAdminCleanup(request, corsHeaders, env) {
  try {
    console.log('🕐 [ADMIN] Manual cleanup triggered');
    const cleanupResult = await cleanupTimeoutAssignments(env);
    
    return new Response(JSON.stringify({
      success: true,
      message: 'Cleanup completed',
      result: cleanupResult
    }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('❌ [ADMIN] Cleanup error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Internal Server Error',
      message: error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 🆕 v2.5.11: Admin手动清理重复分配
async function handleAdminCleanupDuplicates(request, corsHeaders, env) {
  try {
    console.log('🔍 [ADMIN] Manual duplicate cleanup triggered');
    
    let scanned = 0;
    let cleanedUp = 0;
    let kept = 0;
    let groupsReleased = 0;
    let progressArchived = 0;
    
    // 统计：Map<participant_id, Assignment[]>
    const participantMap = new Map();
    
    // 1️⃣ 扫描所有 assignment
    const assignmentKeys = await env.ARC_DATA.list({ prefix: 'assignment_' });
    
    for (const key of assignmentKeys.keys) {
      scanned++;
      const assignmentJson = await env.ARC_DATA.get(key.name);
      if (!assignmentJson) continue;
      
      try {
        const assignment = JSON.parse(assignmentJson);
        const sessionId = key.name.replace('assignment_', '');
        
        // 只处理"进行中"的分配
        if (assignment.status !== 'assigned') continue;
        
        const participantId = assignment.participant_id;
        if (!participantId) continue;  // 跳过没有 participant_id 的
        
        // 按 participant_id 分组
        if (!participantMap.has(participantId)) {
          participantMap.set(participantId, []);
        }
        
        participantMap.get(participantId).push({
          session_id: sessionId,
          assignment: assignment,
          assigned_at: assignment.assigned_at || assignment.created_at
        });
      } catch (parseError) {
        console.error(`Failed to parse assignment ${key.name}:`, parseError);
      }
    }
    
    // 2️⃣ 处理每个 participant 的重复分配
    for (const [participantId, assignments] of participantMap.entries()) {
      if (assignments.length <= 1) continue;  // 没有重复
      
      // 🔧 v2.5.12: 按时间排序（最早的在前）- 保留最早分配的 URL
      assignments.sort((a, b) => {
        const dateA = new Date(a.assigned_at || 0);
        const dateB = new Date(b.assigned_at || 0);
        return dateA.getTime() - dateB.getTime();  // 正序：最早的在前
      });
      
      // 保留最早的一个（第一次分配的 URL）
      const keepAssignment = assignments[0];
      kept++;
      
      console.log(`🔍 [DUPLICATE] Participant ${participantId} has ${assignments.length} assignments, keeping earliest ${keepAssignment.session_id} (${keepAssignment.assigned_at})`);
      
      // 清理其他的
      for (let i = 1; i < assignments.length; i++) {
        const duplicateAssignment = assignments[i];
        const sessionId = duplicateAssignment.session_id;
        const testGroup = duplicateAssignment.assignment.test_group_file || duplicateAssignment.assignment.test_group;
        
        console.log(`  ❌ Cleaning duplicate: ${sessionId} (${testGroup})`);
        
        // 1️⃣ 释放测试组
        if (testGroup) {
          await env.ARC_DATA.delete(`used_${testGroup}`);
          groupsReleased++;
        }
        
        // 2️⃣ 归档进度数据
        const progressKey = `progress_${sessionId}`;
        const progressJson = await env.ARC_DATA.get(progressKey);
        if (progressJson) {
          const archiveKey = `progress_archived_${sessionId}_duplicate_${new Date().toISOString().replace(/[:.]/g, '')}`;
          await env.ARC_DATA.put(archiveKey, progressJson);
          await env.ARC_DATA.delete(progressKey);
          progressArchived++;
        }
        
        // 3️⃣ 删除分配锁
        const lockKey = `assign_lock_${participantId}`;
        await env.ARC_DATA.delete(lockKey);
        
        // 4️⃣ 更新 assignment 状态为 'duplicate_cleaned'
        const assignmentKey = `assignment_${sessionId}`;
        const updatedAssignment = {
          ...duplicateAssignment.assignment,
          status: 'duplicate_cleaned',
          cleaned_at: new Date().toISOString(),
          kept_session_id: keepAssignment.session_id,
          reason: `Duplicate assignment for participant ${participantId}, kept most recent`
        };
        await env.ARC_DATA.put(assignmentKey, JSON.stringify(updatedAssignment));
        
        // 5️⃣ 更新 session 状态
        const sessionKey = `session_${sessionId}`;
        const sessionJson = await env.ARC_DATA.get(sessionKey);
        if (sessionJson) {
          const session = JSON.parse(sessionJson);
          session.status = 'duplicate_cleaned';
          session.cleaned_at = new Date().toISOString();
          session.kept_session_id = keepAssignment.session_id;
          await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
        }
        
        cleanedUp++;
      }
    }
    
    const duplicateParticipants = Array.from(participantMap.entries()).filter(([_, a]) => a.length > 1).length;
    
    const result = {
      scanned,
      duplicate_participants: duplicateParticipants,
      cleaned_up: cleanedUp,
      kept,
      groups_released: groupsReleased,
      progress_archived: progressArchived
    };
    
    console.log(`✅ [ADMIN] Duplicate cleanup completed:`, result);
    
    return new Response(JSON.stringify({
      success: true,
      message: 'Duplicate cleanup completed',
      result
    }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('❌ [ADMIN] Duplicate cleanup error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Internal Server Error',
      message: error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 🆕 v2.5.12: 修正可用测试组
async function handleAdminFixAvailableGroups(request, corsHeaders, env) {
  try {
    console.log('🔧 [ADMIN] Fix available groups triggered');
    
    // 1️⃣ 获取所有测试组文件（从 R2 Bucket）
    const listed = await env.ARC_BUCKET.list({ prefix: 'test/' });
    const allTestGroups = listed.objects
      .map(obj => obj.key.replace('test/', ''))
      .filter(name => name.match(/^test_group\d+\.json$/));
    const totalGroups = allTestGroups.length;
    console.log(`   Total test groups: ${totalGroups}`);
    
    // 2️⃣ 获取所有已使用的测试组（assigned 和 completed）- 并行处理
    const usedTestGroups = new Set();
    let assignedCount = 0;
    let completedCount = 0;
    const assignmentList = await env.ARC_DATA.list({ prefix: 'assignment_' });
    
    console.log(`   🚀 Parallel checking ${assignmentList.keys.length} assignments...`);
    const assignmentPromises = assignmentList.keys.map(async (key) => {
      try {
        const assignmentJson = await env.ARC_DATA.get(key.name);
        if (!assignmentJson) return { testGroup: null, status: null };
        
        const assignment = JSON.parse(assignmentJson);
        
        // 计算已使用的测试组：进行中 + 已完成
        if (assignment.status === 'assigned' || assignment.status === 'completed') {
          const testGroup = assignment.test_group_file || assignment.test_group;
          return { testGroup: testGroup || null, status: assignment.status };
        }
        return { testGroup: null, status: null };
      } catch (error) {
        console.error(`Failed to parse ${key.name}:`, error);
        return { testGroup: null, status: null };
      }
    });
    
    const assignmentResults = await Promise.all(assignmentPromises);
    assignmentResults.forEach(result => {
      if (result.testGroup) {
        usedTestGroups.add(result.testGroup);
        if (result.status === 'assigned') assignedCount++;
        if (result.status === 'completed') completedCount++;
      }
    });
    
    console.log(`   Used test groups: ${usedTestGroups.size} (assigned: ${assignedCount}, completed: ${completedCount})`);
    
    // 3️⃣ 计算真正可用的测试组
    const availableGroups = allTestGroups.filter(group => !usedTestGroups.has(group));
    
    console.log(`   Calculated available groups: ${availableGroups.length}`);
    
    // 4️⃣ 获取修正前的可用测试组
    const beforeAvailableJson = await env.ARC_DATA.get('available_test_groups');
    const beforeAvailable = beforeAvailableJson ? JSON.parse(beforeAvailableJson) : [];
    
    console.log(`   Before fix - available: ${beforeAvailable.length}`);
    
    // 5️⃣ 检测并修正 used_ 键的问题 - 只添加缺失的，不删除
    console.log(`   🔍 Checking and adding missing used_ keys (parallel)...`);
    let usedKeysAdded = 0;
    let missingUsedKeys = [];
    
    // 5.1 并行检查所有已使用的测试组（assigned + completed），添加缺失的 used_ 键
    const addUsedKeyPromises = Array.from(usedTestGroups).map(async (testGroup) => {
      const usedKey = `used_${testGroup}`;
      const usedValue = await env.ARC_DATA.get(usedKey);
      
      if (!usedValue) {
        // 测试组已使用但缺少 used_ 键 → 添加
        await env.ARC_DATA.put(usedKey, 'true');
        console.log(`   ➕ Added missing used_ key: ${usedKey}`);
        return testGroup;
      }
      return null;
    });
    
    const addResults = await Promise.all(addUsedKeyPromises);
    addResults.forEach(testGroup => {
      if (testGroup) {
        usedKeysAdded++;
        missingUsedKeys.push(testGroup);
      }
    });
    
    // 🛡️ 安全模式：不删除任何 used_ 键（避免读取错误导致的灾难）
    console.log(`   🛡️ Safety mode: NOT deleting any used_ keys`);
    console.log(`   💡 To clean up wrong used_ keys, use Admin Dashboard manually`);
    
    // 6️⃣ 检测 available_test_groups 列表中的问题
    const duplicatesRemoved = beforeAvailable.length - new Set(beforeAvailable).size;
    const usedInAvailable = beforeAvailable.filter(g => usedTestGroups.has(g));
    
    // 7️⃣ 更新可用测试组列表
    await env.ARC_DATA.put('available_test_groups', JSON.stringify(availableGroups));
    
    console.log(`   ✅ Fixed available_test_groups: ${availableGroups.length} groups`);
    console.log(`   ✅ Added ${usedKeysAdded} missing used_ keys`);
    
    // 8️⃣ 生成详细信息
    let details = '';
    if (duplicatesRemoved > 0) {
      details += `发现 ${duplicatesRemoved} 个重复项\n`;
    }
    if (usedInAvailable.length > 0) {
      details += `发现 ${usedInAvailable.length} 个已使用但在可用列表中的测试组\n`;
      details += `示例: ${usedInAvailable.slice(0, 3).join(', ')}${usedInAvailable.length > 3 ? '...' : ''}\n`;
    }
    if (usedKeysAdded > 0) {
      details += `添加 ${usedKeysAdded} 个缺失的 used_ 键（防止重复分配）\n`;
      details += `示例: ${missingUsedKeys.slice(0, 3).join(', ')}${missingUsedKeys.length > 3 ? '...' : ''}\n`;
    }
    if (!details) {
      details = '未发现问题，数据已是一致状态';
    }
    
    const result = {
      total_groups: totalGroups,
      before_available: beforeAvailable.length,
      after_available: availableGroups.length,
      assigned_count: assignedCount,
      completed_count: completedCount,
      used_total: usedTestGroups.size,
      duplicates_removed: duplicatesRemoved,
      used_removed: usedInAvailable.length,
      used_keys_added: usedKeysAdded,
      details: details
    };
    
    console.log('   Result:', result);
    
    return new Response(JSON.stringify({
      success: true,
      message: 'Available groups fixed',
      result: result
    }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    console.error('❌ [ADMIN] Fix available groups error:', error);
    return new Response(JSON.stringify({ 
      success: false,
      error: 'Internal Server Error',
      message: error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 导出所有结果
async function handleAdminExport(request, corsHeaders, env) {
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `arc_export_${timestamp}.json`;
    
    // 收集所有结果
    const allResults = [];
    const resultKeys = await env.ARC_RESULTS.list();
    
    for (const key of resultKeys.keys) {
      const resultJson = await env.ARC_RESULTS.get(key.name);
      if (resultJson) {
        try {
          const result = JSON.parse(resultJson);
          allResults.push({
            key: key.name,
            ...result
          });
        } catch (parseError) {
          console.error(`Failed to parse result ${key.name}:`, parseError);
        }
      }
    }
    
    // 保存到 R2
    const exportData = JSON.stringify(allResults, null, 2);
    await env.ARC_BUCKET.put(`exports/${filename}`, exportData);
    
    return new Response(JSON.stringify({
      success: true,
      filename,
      count: allResults.length,
      download_url: `/json/exports/${filename}`
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Export results error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to export results',
      message: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 🆕 查询被试答案（公开访问）
async function handleQueryAnswers(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const participantId = url.searchParams.get('participant_id');

    if (!participantId) {
      return new Response(JSON.stringify({
        error: 'Missing participant_id parameter'
      }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    console.log(`🔍 [QUERY ANSWERS] Participant: ${participantId}`);

    // 🚀 v2.5.20: 并行查询所有 assignment 记录
    const assignmentList = await env.ARC_DATA.list({ prefix: 'assignment_' });
    
    // 并行查询所有 assignments
    const assignmentPromises = assignmentList.keys.map(async (key) => {
      const assignmentJson = await env.ARC_DATA.get(key.name);
      if (assignmentJson) {
        const assignment = JSON.parse(assignmentJson);
        if (assignment.participant_id === participantId || 
            assignment.user_nickname === participantId) {
          return assignment;
        }
      }
      return null;
    });

    const results = await Promise.all(assignmentPromises);
    const userAssignment = results.find(r => r !== null);

    if (!userAssignment) {
      return new Response(JSON.stringify({
        error: 'not_found',
        message: 'No test results found for this participant ID'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    if (userAssignment.status !== 'completed') {
      return new Response(JSON.stringify({
        error: 'not_completed',
        message: 'Test has not been completed yet',
        status: userAssignment.status
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 获取结果数据
    const resultId = userAssignment.result_id;
    if (!resultId) {
      return new Response(JSON.stringify({
        error: 'no_result',
        message: 'No result data available'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 尝试从 KV 读取
    let resultData = null;
    const kvResultJson = await env.ARC_RESULTS.get(resultId);
    
    if (kvResultJson) {
      resultData = JSON.parse(kvResultJson);
      console.log('  ✓ Result found in KV');
    } else {
      // 尝试从 R2 读取
      const r2Key = `results/${resultId}.json`;
      const r2Object = await env.ARC_BUCKET.get(r2Key);
      
      if (r2Object) {
        const r2Text = await r2Object.text();
        resultData = JSON.parse(r2Text);
        console.log('  ✓ Result found in R2');
      }
    }

    if (!resultData) {
      return new Response(JSON.stringify({
        error: 'result_not_found',
        message: 'Result data not found in storage'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 读取测试组数据
    const testGroupFile = userAssignment.test_group_file || userAssignment.test_group;
    let testGroupData = null;
    
    if (testGroupFile) {
      const r2Key = testGroupFile.startsWith('test/') ? testGroupFile : `test/${testGroupFile}`;
      const testGroupObject = await env.ARC_BUCKET.get(r2Key);
      
      if (testGroupObject) {
        const testGroupText = await testGroupObject.text();
        testGroupData = JSON.parse(testGroupText);
        console.log('  ✓ Test group found in R2');
      } else {
        console.log('  ⚠ Test group not found in R2:', r2Key);
      }
    }

    // 返回数据
    return new Response(JSON.stringify({
      success: true,
      assignment: {
        session_id: userAssignment.session_id,
        test_group: userAssignment.test_group_file || userAssignment.test_group,
        test_group_file: userAssignment.test_group_file,
        participant_id: userAssignment.participant_id,
        user_nickname: userAssignment.user_nickname
      },
      result: resultData,
      test_data: testGroupData
    }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Query answers error:', error);
    return new Response(JSON.stringify({
      error: 'server_error',
      message: 'Failed to query answers'
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 下载单个结果
async function handleAdminDownload(request, corsHeaders, env, sessionId) {
  try {
    console.log(`� [ADMIN DOWNLOAD] Session: ${sessionId}`);
    
    // ✅ 步骤 1: 从 assignment 记录中获取 result_id
    const assignmentKey = `assignment_${sessionId}`;
    const assignmentJson = await env.ARC_DATA.get(assignmentKey);
    
    if (!assignmentJson) {
      console.error(`  ✗ Assignment not found: ${assignmentKey}`);
      return new Response(JSON.stringify({
        error: 'Assignment not found',
        message: `No assignment record found for Session ID: ${sessionId}`
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    const assignment = JSON.parse(assignmentJson);
    const resultId = assignment.result_id;
    
    if (!resultId) {
      console.error(`  ✗ No result_id in assignment (status: ${assignment.status})`);
      return new Response(JSON.stringify({
        error: 'Result not found',
        message: `Assignment exists but no result has been submitted yet. Status: ${assignment.status}`,
        status: assignment.status
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    console.log(`  ✓ Found result_id: ${resultId}`);
    
    // ✅ 步骤 2: 优先从 ARC_RESULTS (KV) 获取
    let resultJson = null;
    
    if (env.ARC_RESULTS) {
      resultJson = await env.ARC_RESULTS.get(resultId);
      if (resultJson) {
        console.log(`  ✓ Found result in ARC_RESULTS KV`);
      } else {
        console.log(`  ⚠️ Result not found in ARC_RESULTS KV, trying R2...`);
      }
    }
    
    // ✅ 步骤 3: 如果 KV 中没有，尝试从 R2 获取
    if (!resultJson && env.ARC_BUCKET) {
      try {
        const r2Object = await env.ARC_BUCKET.get(`results/${resultId}.json`);
        if (r2Object) {
          resultJson = await r2Object.text();
          console.log(`  ✓ Found result in R2 Bucket`);
        } else {
          console.log(`  ⚠️ Result not found in R2 Bucket either`);
        }
      } catch (r2Error) {
        console.error(`  ✗ R2 error:`, r2Error.message);
      }
    }
    
    // 如果仍然找不到结果
    if (!resultJson) {
      console.error(`  ✗ Result not found in any storage: ${resultId}`);
      return new Response(JSON.stringify({
        error: 'Result not found',
        message: `Result ID ${resultId} not found in KV or R2 storage`,
        result_id: resultId,
        hint: 'The result may have been archived or deleted'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    console.log(`  ✓ Downloading result: ${resultId}`);
    
    // 返回结果文件
    return new Response(resultJson, {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="result_${sessionId}_${resultId}.json"`
      }
    });
    
  } catch (error) {
    console.error('❌ [ADMIN DOWNLOAD] Error:', error);
    return new Response(JSON.stringify({
      error: 'Failed to download result',
      message: error.message,
      stack: error.stack
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// 重新分配已完成的URL
async function handleAdminReassign(request, corsHeaders, env, sessionId) {
  try {
    const assignmentKey = `assignment_${sessionId}`;
    const sessionKey = `session_${sessionId}`;
    
    const assignmentJson = await env.ARC_DATA.get(assignmentKey);
    const sessionJson = await env.ARC_DATA.get(sessionKey);
    
    if (!assignmentJson && !sessionJson) {
      return new Response(JSON.stringify({
        success: false,
        message: 'Session not found'
      }), {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
    
    // 🔧 v2.5.11: 从 session 或 assignment 获取信息
    let testGroup = null;
    let status = null;
    let participantId = null;
    
    if (sessionJson) {
      const session = JSON.parse(sessionJson);
      testGroup = session.test_group;
      status = session.status;
      participantId = session.participant_id;
    }
    
    if (assignmentJson) {
      const assignment = JSON.parse(assignmentJson);
      testGroup = testGroup || assignment.test_group_file || assignment.test_group;
      status = status || assignment.status;
      participantId = participantId || assignment.participant_id;
    }
    
    // 🆕 v2.5.11: 允许重新分配所有状态（包括进行中），但给予警告
    const isInProgress = (status === 'assigned');
    
    console.log(`🔄 Reassigning session ${sessionId}: status=${status}, testGroup=${testGroup}`);
    
    // 🔧 v2.5.11: 清理所有 4 个 KV 键
    
    // 1️⃣ 释放测试组（删除 used_ 标记）
    if (testGroup) {
      await env.ARC_DATA.delete(`used_${testGroup}`);
      console.log(`  ✅ Deleted used_${testGroup}`);
    }
    
    // 2️⃣ 归档进度数据（如果存在）
    const progressKey = `progress_${sessionId}`;
    const progressJson = await env.ARC_DATA.get(progressKey);
    if (progressJson) {
      const archiveKey = `progress_archived_${sessionId}_reassigned_${new Date().toISOString().replace(/[:.]/g, '')}`;
      await env.ARC_DATA.put(archiveKey, progressJson);
      await env.ARC_DATA.delete(progressKey);
      console.log(`  ✅ Archived progress_${sessionId} → ${archiveKey}`);
    }
    
    // 3️⃣ 删除分配锁（如果存在）
    if (participantId) {
      const lockKey = `assign_lock_${participantId}`;
      await env.ARC_DATA.delete(lockKey);
      console.log(`  ✅ Deleted assign_lock_${participantId}`);
    }
    
    // 4️⃣ 更新 assignment 状态为 'reassigned'（保留历史记录，不删除）
    if (assignmentJson) {
      const assignment = JSON.parse(assignmentJson);
      assignment.status = 'reassigned';
      assignment.reassigned_at = new Date().toISOString();
      assignment.previous_status = status;  // 记录之前的状态
      assignment.locked = false;  // 解锁，允许重新分配
      await env.ARC_DATA.put(assignmentKey, JSON.stringify(assignment));
      console.log(`  ✅ Updated assignment_${sessionId}: ${status} → reassigned`);
    }
    
    // 5️⃣ 更新 session 状态为 'reassigned'（保留历史记录，不删除）
    if (sessionJson) {
      const session = JSON.parse(sessionJson);
      session.status = 'reassigned';
      session.reassigned_at = new Date().toISOString();
      session.previous_status = status;  // 记录之前的状态
      await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
      console.log(`  ✅ Updated session_${sessionId}: ${status} → reassigned`);
    }
    
    console.log(`✅ Reassigned session ${sessionId}: ${testGroup} (status: ${status} → reassigned)`);
    
    return new Response(JSON.stringify({
      success: true,
      message: `Session ${sessionId} marked for reassignment, test group ${testGroup} released`,
      test_group: testGroup,
      previous_status: status,
      was_in_progress: isInProgress,
      cleaned_keys: {
        used_key: testGroup ? `used_${testGroup}` : null,
        progress_key: progressJson ? progressKey : null,
        assign_lock: participantId ? `assign_lock_${participantId}` : null,
        assignment_key: assignmentKey,
        session_key: sessionKey
      }
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Reassign session error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to reassign session',
      message: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// ========================================
// 新增 Pages Functions 兼容端点
// ========================================

// /api/health - 健康检查
async function handleHealth(request, corsHeaders, env) {
  try {
    const health = {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      environment: env.ENVIRONMENT || 'production',
      checks: {
        kv_data: false,
        kv_results: false,
        r2_bucket: false
      }
    };

    // 检查 KV 命名空间
    try {
      if (env.ARC_DATA) {
        await env.ARC_DATA.get('health_check');
        health.checks.kv_data = true;
      }
    } catch (error) {
      console.error('KV_DATA check failed:', error);
    }

    try {
      if (env.ARC_RESULTS) {
        await env.ARC_RESULTS.get('health_check');
        health.checks.kv_results = true;
      }
    } catch (error) {
      console.error('KV_RESULTS check failed:', error);
    }

    // 检查 R2 存储桶
    try {
      if (env.ARC_BUCKET) {
        await env.ARC_BUCKET.list({ limit: 1 });
        health.checks.r2_bucket = true;
      }
    } catch (error) {
      console.error('R2 check failed:', error);
    }

    // 确定整体健康状态
    const allHealthy = Object.values(health.checks).every(check => check === true);
    if (!allHealthy) {
      health.status = 'degraded';
    }

    return new Response(JSON.stringify(health), {
      status: allHealthy ? 200 : 503,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Health check error:', error);
    return new Response(JSON.stringify({
      status: 'error',
      message: error.message,
      timestamp: new Date().toISOString()
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// /api/test-data - 获取测试数据
async function handleTestData(request, corsHeaders, env) {
  try {
    const url = new URL(request.url);
    const filename = url.searchParams.get('filename');

    if (!env.ARC_BUCKET) {
      return new Response(JSON.stringify({
        success: false,
        error: 'R2 bucket not available'
      }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 如果指定了文件名，返回该文件内容
    if (filename) {
      const key = `test/${filename}`;
      const object = await env.ARC_BUCKET.get(key);

      if (!object) {
        return new Response(JSON.stringify({
          success: false,
          error: 'Test data file not found'
        }), {
          status: 404,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const content = await object.text();
      let testData;
      try {
        testData = JSON.parse(content);
      } catch (error) {
        return new Response(JSON.stringify({
          success: false,
          error: 'Invalid JSON in test data file'
        }), {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      return new Response(JSON.stringify({
        success: true,
        filename: filename,
        data: testData
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // 如果没有指定文件名，返回可用文件列表
    const listed = await env.ARC_BUCKET.list({ prefix: 'test/' });
    
    const files = listed.objects
      .filter(obj => obj.key.endsWith('.json'))
      .map(obj => ({
        name: obj.key.split('/').pop(),
        path: obj.key,
        size: obj.size,
        uploaded: obj.uploaded.toISOString(),
        url: `/api/test-data?filename=${obj.key.split('/').pop()}`
      }));

    return new Response(JSON.stringify({
      success: true,
      count: files.length,
      files: files
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Test data API error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Failed to get test data: ' + error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
}

// /api/save_results - 保存结果（兼容性端点）
// ⚠️ v2.5.2: 重定向到 handleSubmitResults 以确保状态正确更新
async function handleSaveResults(request, corsHeaders, env) {
  console.log('📝 [REDIRECT] /api/save_results → handleSubmitResults');
  // 直接调用 handleSubmitResults，它有完整的状态管理逻辑
  return handleSubmitResults(request, corsHeaders, env);
}

// ========================================
// 🕐 自动清理超时分配的函数
// ========================================
/**
 * 扫描所有 assignment 并回收超过 48 小时的分配
 * 由 Cron Trigger 定时调用 (每 6 小时)
 * @param {Object} env - Worker 环境变量
 * @returns {Object} - 清理结果统计
 */
async function cleanupTimeoutAssignments(env) {
  const startTime = Date.now();
  let cleanedCount = 0;
  let errorCount = 0;
  const cleanedAssignments = [];
  const errors = [];
  
  console.log('🔍 [CLEANUP] Scanning all assignments for timeouts...');
  
  try {
    // 获取所有 assignment_ 键
    const assignmentList = await env.ARC_DATA.list({ prefix: 'assignment_' });
    console.log(`   Found ${assignmentList.keys.length} assignments to check`);
    
    for (const key of assignmentList.keys) {
      try {
        const sessionId = key.name.replace('assignment_', '');
        const assignmentJson = await env.ARC_DATA.get(key.name);
        
        if (!assignmentJson) {
          console.log(`   ⚠️ Skipping ${sessionId}: assignment data not found`);
          continue;
        }
        
        const assignment = JSON.parse(assignmentJson);
        
        // 🔧 跳过已完成、已超时、已失败、已清理、已重新分配的分配
        // 这些状态的测试组已经被释放，不应再次处理
        if (assignment.status === 'completed' || 
            assignment.status === 'timeout_locked' || 
            assignment.status === 'attention_check_failed' || 
            assignment.status === 'duplicate_cleaned' || 
            assignment.status === 'reassigned') {
          continue;
        }
        
        // 检查是否超时
        const timeoutCheck = checkUrlTimeout(assignment);
        
        if (timeoutCheck.is_timeout) {
          console.log(`   ⏰ Recycling timeout assignment: ${sessionId}`);
          console.log(`      Test Group: ${assignment.test_group_file}`);
          console.log(`      Assigned At: ${assignment.assigned_at || assignment.created_at}`);
          console.log(`      Elapsed: ${timeoutCheck.elapsed_hours} hours`);
          
          // 标记为超时
          assignment.status = 'timeout_locked';
          assignment.timeout_at = timeoutCheck.timeout_at;
          assignment.cleaned_by_cron = true;
          assignment.cleaned_at = new Date().toISOString();
          
          // 归档进度文件
          await archiveSavedProgress(env, sessionId, assignment.participant_id, 'timeout_cron');
          
          // 更新 session_ 状态为 timeout_locked（保留记录而非删除）
          const sessionKey = `session_${sessionId}`;
          const sessionJson = await env.ARC_DATA.get(sessionKey);
          if (sessionJson) {
            const session = JSON.parse(sessionJson);
            session.status = 'timeout_locked';
            session.timeout_at = timeoutCheck.timeout_at;
            session.cleaned_by_cron = true;
            await env.ARC_DATA.put(sessionKey, JSON.stringify(session));
            console.log(`      ✓ Updated session_${sessionId} status to timeout_locked`);
          } else {
            console.log(`      ⚠️ session_${sessionId} not found`);
          }
          
          // 删除 used_ 键（释放测试组）
          const testGroup = assignment.test_group_file || assignment.test_group;
          if (testGroup) {
            await env.ARC_DATA.delete(`used_${testGroup}`);
          }
          
          // 归档 progress_ 键
          const progressKey = `progress_${sessionId}`;
          const progressData = await env.ARC_DATA.get(progressKey);
          if (progressData) {
            const archiveKey = `progress_archived_${sessionId}_timeout_cron_${assignment.timeout_at.replace(/[:.]/g, '')}`;
            await env.ARC_DATA.put(archiveKey, progressData);
            await env.ARC_DATA.delete(progressKey);
          }
          
          // 保存更新后的 assignment
          await env.ARC_DATA.put(key.name, JSON.stringify(assignment));
          
          cleanedCount++;
          cleanedAssignments.push({
            session_id: sessionId,
            test_group: testGroup,
            elapsed_hours: timeoutCheck.elapsed_hours,
            assigned_at: assignment.assigned_at || assignment.created_at
          });
          
          console.log(`      ✓ Cleaned successfully`);
        }
        
      } catch (error) {
        errorCount++;
        errors.push({
          key: key.name,
          error: error.message
        });
        console.error(`   ✗ Error cleaning ${key.name}:`, error.message);
      }
    }
    
    const duration = Date.now() - startTime;
    
    console.log(`✅ [CLEANUP] Scan completed`);
    console.log(`   Total checked: ${assignmentList.keys.length}`);
    console.log(`   Cleaned: ${cleanedCount}`);
    console.log(`   Errors: ${errorCount}`);
    console.log(`   Duration: ${duration}ms`);
    
    return {
      success: true,
      total_checked: assignmentList.keys.length,
      cleaned_count: cleanedCount,
      error_count: errorCount,
      duration_ms: duration,
      cleaned_assignments: cleanedAssignments,
      errors: errors
    };
    
  } catch (error) {
    console.error('❌ [CLEANUP] Fatal error:', error);
    
    return {
      success: false,
      error: error.message,
      cleaned_count: cleanedCount,
      error_count: errorCount,
      duration_ms: Date.now() - startTime
    };
  }
}

// ========================================
// 🆕 v2.5.16: 测试组状态诊断端点
// ========================================
async function handleDebugTestGroupsStatus(request, corsHeaders, env) {
  console.log('🔍 [DEBUG] Testing groups status check requested');
  
  try {
    const startTime = Date.now();
    
    // 检查所有 200 个测试组的状态
    const usedGroups = [];
    const availableGroups = [];
    
    for (let i = 1; i <= 200; i++) {
      const groupName = `test_group${i}.json`;
      const usedKey = `used_${groupName}`;
      const usedValue = await env.ARC_DATA.get(usedKey);
      
      if (usedValue) {
        usedGroups.push({
          group: groupName,
          session_id: usedValue,
          index: i
        });
      } else {
        availableGroups.push({
          group: groupName,
          index: i
        });
      }
    }
    
    const duration = Date.now() - startTime;
    
    console.log(`✅ [DEBUG] Status check completed in ${duration}ms`);
    console.log(`   Total: 200 groups`);
    console.log(`   Used: ${usedGroups.length}`);
    console.log(`   Available: ${availableGroups.length}`);
    
    // 返回友好的 HTML 响应
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Groups Status - ARCANA Debug</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #0f172a;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255,255,255,0.96);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(2,6,23,0.35);
        }
        h1 { color: #4f46e5; margin-bottom: 10px; }
        .subtitle { color: #6b7280; font-size: 14px; margin-bottom: 30px; }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .stat-card.total { border-color: #3b82f6; background: #eff6ff; }
        .stat-card.used { border-color: #ef4444; background: #fee2e2; }
        .stat-card.available { border-color: #10b981; background: #d1fae5; }
        .stat-value {
            font-size: 36px;
            font-weight: 700;
            margin: 10px 0;
        }
        .stat-label {
            font-size: 14px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .progress-bar {
            background: #e5e7eb;
            border-radius: 10px;
            height: 30px;
            overflow: hidden;
            margin: 20px 0;
            position: relative;
        }
        .progress-fill {
            background: linear-gradient(90deg, #10b981 0%, #06b6d4 100%);
            height: 100%;
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            font-size: 14px;
        }
        .details {
            margin-top: 30px;
        }
        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin: 20px 0 10px 0;
            color: #1f2937;
        }
        .group-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 8px;
            margin-top: 15px;
        }
        .group-item {
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            text-align: center;
        }
        .group-used {
            background: #fee2e2;
            border: 1px solid #fca5a5;
            color: #991b1b;
        }
        .group-available {
            background: #d1fae5;
            border: 1px solid #6ee7b7;
            color: #065f46;
        }
        .timestamp {
            text-align: center;
            margin-top: 30px;
            color: #9ca3af;
            font-size: 13px;
        }
        .warning {
            background: #fef3c7;
            border: 2px solid #fbbf24;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            color: #78350f;
        }
        .warning strong { color: #92400e; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Test Groups Status</h1>
        <div class="subtitle">ARCANA Cognitive Test Platform - Real-time Diagnostic</div>
        
        <div class="summary">
            <div class="stat-card total">
                <div class="stat-label">Total Groups</div>
                <div class="stat-value">200</div>
            </div>
            <div class="stat-card used">
                <div class="stat-label">Used</div>
                <div class="stat-value">${usedGroups.length}</div>
            </div>
            <div class="stat-card available">
                <div class="stat-label">Available</div>
                <div class="stat-value">${availableGroups.length}</div>
            </div>
        </div>
        
        <div class="progress-bar">
            <div class="progress-fill" style="width: ${(availableGroups.length / 200 * 100).toFixed(1)}%">
                ${(availableGroups.length / 200 * 100).toFixed(1)}% Available
            </div>
        </div>
        
        ${availableGroups.length === 0 ? `
        <div class="warning">
            <strong>⚠️ Critical: All 200 test groups are currently in use!</strong>
            <p style="margin-top: 8px;">No new participants can start tests until some groups are released. Please contact the administrator to clean up completed or timed-out sessions.</p>
        </div>
        ` : ''}
        
        ${availableGroups.length < 20 && availableGroups.length > 0 ? `
        <div class="warning">
            <strong>⚠️ Warning: Only ${availableGroups.length} test groups remaining!</strong>
            <p style="margin-top: 8px;">Consider cleaning up completed sessions soon to prevent assignment failures.</p>
        </div>
        ` : ''}
        
        <div class="details">
            <div class="section-title">📊 Usage Distribution</div>
            <div class="group-grid">
                ${Array.from({length: 200}, (_, i) => {
                    const groupNum = i + 1;
                    const isUsed = usedGroups.some(g => g.index === groupNum);
                    return `<div class="group-item ${isUsed ? 'group-used' : 'group-available'}">
                        Group ${groupNum}
                    </div>`;
                }).join('')}
            </div>
        </div>
        
        <div class="timestamp">
            Generated at: ${new Date().toISOString()}<br>
            Query duration: ${duration}ms
        </div>
    </div>
</body>
</html>`;
    
    return new Response(html, {
      status: 200,
      headers: {
        ...corsHeaders,
        'Content-Type': 'text/html; charset=utf-8'
      }
    });
    
  } catch (error) {
    console.error('❌ [DEBUG] Error checking test groups status:', error);
    
    return new Response(JSON.stringify({
      error: error.message,
      stack: error.stack
    }), {
      status: 500,
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json'
      }
    });
  }
}
