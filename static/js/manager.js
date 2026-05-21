$(document).ready(function () {
    function renderActionButtons(taskId) {
        return `
            <button class="ms-Button ms-Button--primary js-stop-task" data-task-id="${taskId}">结束</button>
            <button class="ms-Button ms-Button--default js-restart-task" data-task-id="${taskId}" style="margin-left: 8px;">重启</button>
        `;
    }

    function postTaskAction(url, successMessage) {
        return $.ajax({
            url: url,
            type: "POST",
            success: function (response) {
                if (response.status === 200) {
                    alert(successMessage);
                    loadTasks();
                } else {
                    alert(response.msg || "操作失败");
                }
            },
            error: function (xhr) {
                alert("请求失败：" + (xhr.responseJSON?.msg || xhr.responseText || "未知错误"));
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
                   if (!tasks || tasks.length === 0) {
                       tbody.append('<tr><td class="ms-Table-cell" colspan="11" style="text-align: center;">暂无任务</td></tr>');
                       return;
                   }
                   tasks.forEach(task => {
                       tbody.append(`
                           <tr data-task-id="${task.id}">
                                <td class="ms-Table-cell">${task.id}</td>
                                <td class="ms-Table-cell">${task.taskname || ''}</td>
                                <td class="ms-Table-cell">${task.udp_port !== null && task.udp_port !== undefined ? task.udp_port : ''}</td>
                                <td class="ms-Table-cell">${task.create_time || ''}</td>
                               <td class="ms-Table-cell">${task.port || ''}</td>  
                               <td class="ms-Table-cell">${task.cam1_ip || ''}</td>
                               <td class="ms-Table-cell">${task.cam1_username || ''}</td>
                               <td class="ms-Table-cell">${task.cam1_password || ''}</td>
                               <td class="ms-Table-cell">${task.url || ''}</td>
                               <td class="ms-Table-cell">${task.event_port || ''}</td>
                               <td class="ms-Table-cell">${renderActionButtons(task.id)}</td>
                            <!--    <td class="ms-Table-cell">${tasks.cam2_ip}</td>
                                <td class="ms-Table-cell">${tasks.cam2_username}</td>
                                <td class="ms-Table-cell">${tasks.cam2_password}</td>
                                <td class="ms-Table-cell">${tasks.cam2_type}</td> -->
                           </tr>
                       `);
                   });
               } else {
                   alert("加载任务列表失败：" + response.msg);
               }
           },
           error: function () {
               alert("请求失败");
           }
       });
   }

   $(document).on('click', '.js-stop-task', function () {
       const taskId = $(this).data('task-id');
       if (!taskId) return;
       if (!confirm('确定要结束并删除该任务记录吗？')) return;
       postTaskAction(`/task/${taskId}/stop`, '结束并删除成功');
   });

   $(document).on('click', '.js-restart-task', function () {
       const taskId = $(this).data('task-id');
       if (!taskId) return;
       if (!confirm('确定要根据当前记录重启该任务吗？')) return;
       postTaskAction(`/task/${taskId}/restart`, '重启成功');
   });

   // 页面加载时调用
   loadTasks();
});