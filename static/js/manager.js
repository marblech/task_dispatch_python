$(document).ready(function () {
    const taskCache = {};
    const pendingTaskActions = {};
    let toastTimer = null;
    let confirmResolver = null;
    let currentLogTaskId = null;

    function initializeAuthState() {
        fetch('/api/auth/status')
            .then(response => response.json())
            .then(data => {
                if (!data.logged_in) {
                    window.location.href = '/login';
                    return;
                }
                $('#userInfo').text(`欢迎, ${data.username || '用户'}`);
            })
            .catch(error => {
                console.error('Check auth status error:', error);
                window.location.href = '/login';
            });
    }

    function bindLogoutAction() {
        $('#logoutBtn').on('click', function () {
            fetch('/logout', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
                .then(() => {
                    window.location.href = '/login';
                })
                .catch(() => {
                    window.location.href = '/login';
                });
        });
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderActionButtons(taskId) {
        const isPending = Boolean(pendingTaskActions[String(taskId)]);
        const disabledAttr = isPending ? 'disabled aria-disabled="true"' : '';
        const disabledClass = isPending ? ' is-disabled' : '';
        return `
            <div class="action-btn-group">
                <button class="task-action-btn task-action-btn--modify js-edit-task" data-task-id="${taskId}" type="button">
                    <span class="task-action-btn__icon ms-Icon ms-Icon--EditNote" aria-hidden="true"></span>
                    <span class="task-action-btn__label">修改</span>
                </button>
                <button class="task-action-btn task-action-btn--stop js-stop-task${disabledClass}" data-task-id="${taskId}" type="button" ${disabledAttr}>
                    <span class="task-action-btn__icon ms-Icon ms-Icon--Stop" aria-hidden="true"></span>
                    <span class="task-action-btn__label">${isPending ? '处理中' : '结束'}</span>
                </button>
                <button class="task-action-btn task-action-btn--restart js-restart-task${disabledClass}" data-task-id="${taskId}" type="button" ${disabledAttr}>
                    <span class="task-action-btn__icon ms-Icon ms-Icon--Refresh" aria-hidden="true"></span>
                    <span class="task-action-btn__label">${isPending ? '处理中' : '重启'}</span>
                </button>
            </div>
        `;
    }

    function renderUrlCell(task) {
        const urlValue = task.url || '';
        if (!urlValue) {
            return '<span class="task-url-empty">--</span>';
        }

        return `
            <button class="task-url-btn js-open-player" data-task-id="${escapeHtml(task.id)}" type="button" title="点击播放视频流">
                ${escapeHtml(urlValue)}
            </button>
        `;
    }

    function renderLogCell(task) {
        if (!task.log_file) {
            return '<span class="task-url-empty">--</span>';
        }

        return `
            <button class="task-action-btn task-action-btn--log js-view-log" data-task-id="${escapeHtml(task.id)}" type="button" title="${escapeHtml(task.log_file)}">
                <span class="task-action-btn__icon ms-Icon ms-Icon--TextDocument" aria-hidden="true"></span>
                <span class="task-action-btn__label">查看日志</span>
            </button>
        `;
    }

    function setTaskActionPending(taskId, isPending) {
        const taskKey = String(taskId);
        if (isPending) {
            pendingTaskActions[taskKey] = true;
        } else {
            delete pendingTaskActions[taskKey];
        }

        const row = $(`#task-list-body tr[data-task-id="${taskKey}"]`);
        if (!row.length) {
            return;
        }

        const stopButton = row.find('.js-stop-task');
        const restartButton = row.find('.js-restart-task');
        const labelText = isPending ? '处理中' : null;

        stopButton.prop('disabled', isPending).attr('aria-disabled', String(isPending)).toggleClass('is-disabled', isPending);
        restartButton.prop('disabled', isPending).attr('aria-disabled', String(isPending)).toggleClass('is-disabled', isPending);

        if (isPending) {
            stopButton.find('.task-action-btn__label').text(labelText);
            restartButton.find('.task-action-btn__label').text(labelText);
        } else {
            stopButton.find('.task-action-btn__label').text('结束');
            restartButton.find('.task-action-btn__label').text('重启');
        }
    }

    function hideToast() {
        $('#taskToast').removeClass('show success error');
        if (toastTimer) {
            clearTimeout(toastTimer);
            toastTimer = null;
        }
    }

    function showToast(type, title, message) {
        const toast = $('#taskToast');
        const isError = type === 'error';
        $('#taskToastIcon').text(isError ? '✖' : '✔');
        $('#taskToastTitle').text(title || (isError ? '操作失败' : '操作成功'));
        $('#taskToastBody').text(message || '');
        toast.removeClass('success error').addClass(type).addClass('show');
        if (toastTimer) {
            clearTimeout(toastTimer);
        }
        toastTimer = setTimeout(function () {
            hideToast();
        }, 4000);
    }

    function setConfirmVisible(visible) {
        const modal = $('#taskConfirmModal');
        modal.toggleClass('show', visible);
        modal.attr('aria-hidden', visible ? 'false' : 'true');
    }

    function resolveConfirm(result) {
        if (confirmResolver) {
            const currentResolver = confirmResolver;
            confirmResolver = null;
            currentResolver(result);
        }
        setConfirmVisible(false);
    }

    function showConfirmDialog(title, message) {
        $('#taskConfirmTitle').text(title || '请确认操作');
        $('#taskConfirmBody').text(message || '确认要继续执行当前操作吗？');
        setConfirmVisible(true);
        return new Promise(function (resolve) {
            confirmResolver = resolve;
        });
    }

    function setModalVisible(visible) {
        const modal = $('#editTaskModal');
        modal.toggleClass('show', visible);
        modal.attr('aria-hidden', visible ? 'false' : 'true');
    }

    function closeEditModal() {
        $('#editTaskForm')[0].reset();
        $('#editTaskId').val('');
        setModalVisible(false);
    }

    function setLogModalVisible(visible) {
        const modal = $('#taskLogModal');
        modal.toggleClass('show', visible);
        modal.attr('aria-hidden', visible ? 'false' : 'true');
    }

    function updateLogModal(task, options) {
        const taskLabel = task && (task.taskname || `任务 ${task.id}`);
        $('#taskLogTitle').text(taskLabel ? `${taskLabel} 日志` : '任务日志');
        $('#taskLogPath').text(options.path || (task && task.log_file) || '未选择日志文件');
        $('#taskLogStatus').text(options.status || '日志已加载');
        $('#taskLogContent').text(options.content || '暂无日志内容');
    }

    function closeLogModal() {
        currentLogTaskId = null;
        updateLogModal(null, {
            path: '未选择日志文件',
            status: '点击“查看日志”后加载内容。',
            content: '暂无日志内容'
        });
        setLogModalVisible(false);
    }

    function openLogModal(task) {
        currentLogTaskId = String(task.id);
        updateLogModal(task, {
            path: task.log_file || '未记录日志文件路径',
            status: '正在加载日志内容...',
            content: '加载中...'
        });
        setLogModalVisible(true);

        $.ajax({
            url: `/task/${encodeURIComponent(task.id)}/log`,
            type: 'GET',
            success: function (response) {
                if (String(task.id) !== currentLogTaskId) {
                    return;
                }

                if (response.status === 200 && response.data) {
                    updateLogModal(task, {
                        path: response.data.log_file || task.log_file || '未记录日志文件路径',
                        status: response.data.content ? '日志加载完成' : '日志文件为空',
                        content: response.data.content || '日志文件为空'
                    });
                } else {
                    const errorMessage = response.msg || '读取日志失败';
                    updateLogModal(task, {
                        path: task.log_file || '未记录日志文件路径',
                        status: errorMessage,
                        content: '未能读取日志内容'
                    });
                    showToast('error', '日志加载失败', errorMessage);
                }
            },
            error: function (xhr) {
                if (String(task.id) !== currentLogTaskId) {
                    return;
                }

                const errorMessage = xhr.responseJSON?.msg || xhr.responseText || '请求失败，请稍后重试';
                updateLogModal(task, {
                    path: task.log_file || '未记录日志文件路径',
                    status: errorMessage,
                    content: '未能读取日志内容'
                });
                showToast('error', '日志加载失败', errorMessage);
            }
        });
    }

    function populateEditForm(task) {
        $('#editTaskId').val(task.id || '');
        $('#editTaskName').val(task.taskname || '');
        $('#editUdpPort').val(task.udp_port ?? '');
        $('#editVideoPort').val(task.port ?? '');
        $('#editEventPort').val(task.event_port ?? '');
        $('#editTestMode').val(String(task.test_mode ?? 0));
        $('#editCam1Ip').val(task.cam1_ip || '');
        $('#editCam1Username').val(task.cam1_username || '');
        $('#editCam1Password').val(task.cam1_password || '');
        $('#editCam1SourceUrl').val(task.cam1_source_url || '');
        $('#editUrl').val(task.url || '');
        setModalVisible(true);
    }

    function normalizeNumber(value) {
        if (value === '' || value === null || value === undefined) {
            return null;
        }
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function postTaskAction(taskId, url, successMessage) {
        setTaskActionPending(taskId, true);
        return $.ajax({
            url: url,
            type: "POST",
            success: function (response) {
                if (response.status === 200) {
                    showToast('success', '操作成功', successMessage);
                    loadTasks();
                } else {
                    showToast('error', '操作失败', response.msg || '操作失败');
                }
            },
            error: function (xhr) {
                showToast('error', '请求失败', xhr.responseJSON?.msg || xhr.responseText || '未知错误');
            },
            complete: function () {
                setTaskActionPending(taskId, false);
            }
        });
    }

    // 动态加载人员列表
    function loadTasks() {
       $.ajax({
           url: "/task_list", // 假设后端提供此接口
           type: "GET",
           success: function (response) {
               if (response.status === 200) {
                   const tasks = response.data;
                   const tbody = $("#task-list-body");
                   tbody.empty(); // 清空表格内容
                   Object.keys(taskCache).forEach(key => delete taskCache[key]);
                   if (!tasks || tasks.length === 0) {
                       tbody.append('<tr><td class="ms-Table-cell table-message-cell" colspan="12">暂无任务</td></tr>');
                       return;
                   }
                   tasks.forEach(task => {
                       taskCache[String(task.id)] = task;
                       tbody.append(`
                           <tr data-task-id="${escapeHtml(task.id)}">
                                <td class="ms-Table-cell">${escapeHtml(task.id)}</td>
                                <td class="ms-Table-cell">${escapeHtml(task.taskname || '')}</td>
                                <td class="ms-Table-cell">${escapeHtml(task.udp_port !== null && task.udp_port !== undefined ? task.udp_port : '')}</td>
                                <td class="ms-Table-cell">${escapeHtml(task.create_time || '')}</td>
                               <td class="ms-Table-cell">${escapeHtml(task.port || '')}</td>  
                               <td class="ms-Table-cell">${escapeHtml(task.cam1_ip || '')}</td>
                               <td class="ms-Table-cell">${escapeHtml(task.cam1_username || '')}</td>
                               <td class="ms-Table-cell">${escapeHtml(task.cam1_password || '')}</td>
                               <td class="ms-Table-cell">${renderUrlCell(task)}</td>
                               <td class="ms-Table-cell">${escapeHtml(task.event_port || '')}</td>
                               <td class="ms-Table-cell">${renderLogCell(task)}</td>
                               <td class="ms-Table-cell">${renderActionButtons(task.id)}</td>
                            <!--    <td class="ms-Table-cell">${tasks.cam2_ip}</td>
                                <td class="ms-Table-cell">${tasks.cam2_username}</td>
                                <td class="ms-Table-cell">${tasks.cam2_password}</td>
                                <td class="ms-Table-cell">${tasks.cam2_type}</td> -->
                           </tr>
                       `);
                   });
               } else {
                   showToast('error', '加载失败', response.msg || '加载任务列表失败');
               }
           },
           error: function () {
               showToast('error', '加载失败', '请求失败，请稍后重试');
           }
       });
   }

   $(document).on('click', '.js-stop-task', async function () {
       const taskId = $(this).data('task-id');
       if (!taskId || $(this).prop('disabled')) return;
       const confirmed = await showConfirmDialog('确认结束任务', '确定要结束并删除该任务记录吗？');
       if (!confirmed) return;
       postTaskAction(taskId, `/task/${taskId}/stop`, '结束并删除成功');
   });

   $(document).on('click', '.js-edit-task', function () {
       const taskId = String($(this).data('task-id'));
       const task = taskCache[taskId];
       if (!task) {
           showToast('error', '打开失败', '未找到任务数据');
           return;
       }
       populateEditForm(task);
   });

   $(document).on('click', '.js-open-player', function () {
       const taskId = String($(this).data('task-id'));
       const task = taskCache[taskId];
       if (!task || !task.url) {
           showToast('error', '播放失败', '该任务没有可用的视频URL');
           return;
       }

       if (!window.managerStreamPlayer || typeof window.managerStreamPlayer.open !== 'function') {
           showToast('error', '播放器不可用', '播放器脚本未正确加载');
           return;
       }

       window.managerStreamPlayer.open(task.url, task.taskname || `任务 ${task.id}`);
   });

   $(document).on('click', '.js-view-log', function () {
       const taskId = String($(this).data('task-id'));
       const task = taskCache[taskId];
       if (!task || !task.log_file) {
           showToast('error', '查看失败', '该任务未记录日志文件路径');
           return;
       }

       openLogModal(task);
   });

   $(document).on('click', '.js-restart-task', async function () {
       const taskId = $(this).data('task-id');
       if (!taskId || $(this).prop('disabled')) return;
       const confirmed = await showConfirmDialog('确认重启任务', '确定要根据当前记录重启该任务吗？');
       if (!confirmed) return;
       postTaskAction(taskId, `/task/${taskId}/restart`, '重启成功');
   });

   $('#cancelEditTaskBtn').on('click', function () {
       closeEditModal();
   });

   $('#editTaskModal').on('click', function (event) {
       if (event.target.id === 'editTaskModal') {
           closeEditModal();
       }
   });

   $('#taskToastClose').on('click', function () {
       hideToast();
   });

   $('#taskConfirmCancelBtn').on('click', function () {
       resolveConfirm(false);
   });

   $('#taskConfirmSubmitBtn').on('click', function () {
       resolveConfirm(true);
   });

   $('#taskConfirmModal').on('click', function (event) {
       if (event.target.id === 'taskConfirmModal') {
           resolveConfirm(false);
       }
   });

   $('#taskLogCloseBtn, #taskLogCloseFooterBtn').on('click', function () {
       closeLogModal();
   });

   $('#taskLogRefreshBtn').on('click', function () {
       if (!currentLogTaskId) {
           return;
       }

       const task = taskCache[currentLogTaskId];
       if (!task) {
           showToast('error', '刷新失败', '未找到任务数据');
           return;
       }

       openLogModal(task);
   });

   $('#taskLogModal').on('click', function (event) {
       if (event.target.id === 'taskLogModal') {
           closeLogModal();
       }
   });

   $(document).on('keydown', function (event) {
       if (event.key === 'Escape' && $('#taskConfirmModal').hasClass('show')) {
           resolveConfirm(false);
           return;
       }
       if (event.key === 'Escape' && $('#taskLogModal').hasClass('show')) {
           closeLogModal();
           return;
       }
       if (event.key === 'Escape' && $('#editTaskModal').hasClass('show')) {
           closeEditModal();
       }
   });

   $('#editTaskForm').on('submit', function (event) {
       event.preventDefault();
       const taskId = $('#editTaskId').val();
       if (!taskId) {
           showToast('error', '保存失败', '任务ID不能为空');
           return;
       }

       const saveButton = $('#saveEditTaskBtn');
       const payload = {
           taskname: $('#editTaskName').val().trim(),
           udp_port: normalizeNumber($('#editUdpPort').val()),
           port: normalizeNumber($('#editVideoPort').val()),
           event_port: normalizeNumber($('#editEventPort').val()),
           test_mode: normalizeNumber($('#editTestMode').val()),
           cam1_ip: $('#editCam1Ip').val().trim(),
           cam1_username: $('#editCam1Username').val().trim(),
           cam1_password: $('#editCam1Password').val().trim(),
           cam1_source_url: $('#editCam1SourceUrl').val().trim(),
           url: $('#editUrl').val().trim()
       };

       saveButton.prop('disabled', true).text('保存中...');

       $.ajax({
           url: `/task/${encodeURIComponent(taskId)}`,
           type: 'PUT',
           contentType: 'application/json',
           data: JSON.stringify(payload),
           success: function (response) {
               if (response.status === 200) {
                   showToast('success', '保存成功', response.msg || '任务信息已更新');
                   closeEditModal();
                   loadTasks();
               } else {
                   showToast('error', '保存失败', response.msg || '修改失败');
               }
           },
           error: function (xhr) {
               showToast('error', '保存失败', xhr.responseJSON?.msg || xhr.responseText || '请求失败，请稍后重试');
           },
           complete: function () {
               saveButton.prop('disabled', false).text('保存');
           }
       });
   });

   // 页面加载时调用
    initializeAuthState();
    bindLogoutAction();
   loadTasks();
});