(function (window, document) {
    const modal = document.getElementById('videoPlayerModal');
    const titleLabel = document.getElementById('videoPlayerTaskLabel');
    const statusElement = document.getElementById('videoPlayerStatus');
    const supportBadge = document.getElementById('videoPlayerSupportBadge');
    const currentUrlElement = document.getElementById('videoPlayerCurrentUrl');
    const videoElement = document.getElementById('videoPlayerElement');
    const closeButton = document.getElementById('videoPlayerCloseBtn');
    const stopButton = document.getElementById('videoPlayerStopBtn');
    const replayButton = document.getElementById('videoPlayerReplayBtn');
    const flvjs = window.flvjs;

    let player = null;
    let currentUrl = '';

    if (!modal || !statusElement || !supportBadge || !currentUrlElement || !videoElement) {
        return;
    }

    function setModalVisible(visible) {
        modal.classList.toggle('show', visible);
        modal.setAttribute('aria-hidden', visible ? 'false' : 'true');
    }

    function setStatus(message, type) {
        statusElement.textContent = message;
        statusElement.classList.remove('is-error', 'is-ok');

        if (type === 'error') {
            statusElement.classList.add('is-error');
        }

        if (type === 'ok') {
            statusElement.classList.add('is-ok');
        }
    }

    function setSupportState() {
        if (!flvjs) {
            supportBadge.textContent = 'flv.js 未加载';
            supportBadge.classList.add('is-unsupported');
            supportBadge.classList.remove('is-supported');
            return false;
        }

        if (!flvjs.isSupported()) {
            supportBadge.textContent = '当前浏览器不支持';
            supportBadge.classList.add('is-unsupported');
            supportBadge.classList.remove('is-supported');
            return false;
        }

        supportBadge.textContent = '当前浏览器支持播放';
        supportBadge.classList.add('is-supported');
        supportBadge.classList.remove('is-unsupported');
        return true;
    }

    function destroyPlayer() {
        if (!player) {
            return;
        }

        try {
            player.pause();
            player.unload();
            player.detachMediaElement();
            player.destroy();
        } catch (error) {
            console.warn('销毁播放器时出现问题:', error);
        }

        player = null;
    }

    function resetVideoElement() {
        videoElement.pause();
        videoElement.removeAttribute('src');
        videoElement.load();
    }

    function normalizeUrl(rawValue) {
        const value = String(rawValue || '').trim();

        if (!value) {
            throw new Error('视频URL不能为空。');
        }

        if (!/^wss?:\/\//i.test(value)) {
            throw new Error('当前播放器仅支持 ws:// 或 wss:// 的 FLV 流地址。');
        }

        return value;
    }

    function attachPlayerEvents(currentPlayer, url) {
        currentPlayer.on(flvjs.Events.ERROR, (_type, detail, info) => {
            console.error('播放器错误:', detail, info);
            setStatus(`播放失败：${detail || '未知错误'}。请检查流地址、服务状态或跨域配置。`, 'error');
        });

        currentPlayer.on(flvjs.Events.LOADING_COMPLETE, () => {
            setStatus(`流已结束：${url}`, 'ok');
        });

        currentPlayer.on(flvjs.Events.RECOVERED_EARLY_EOF, () => {
            setStatus('网络抖动后已自动恢复播放。', 'ok');
        });
    }

    function stopPlayback() {
        destroyPlayer();
        resetVideoElement();
        if (currentUrl) {
            setStatus('已停止播放。');
        }
    }

    async function play(url) {
        const streamUrl = normalizeUrl(url);
        currentUrl = streamUrl;
        currentUrlElement.textContent = streamUrl;

        if (!setSupportState()) {
            throw new Error('当前浏览器或 flv.js 资源不支持播放。');
        }

        destroyPlayer();
        resetVideoElement();
        setStatus(`正在连接：${streamUrl}`);

        player = flvjs.createPlayer(
            {
                type: 'flv',
                url: streamUrl,
                isLive: true,
            },
            {
                enableStashBuffer: false,
                stashInitialSize: 128,
                lazyLoad: false,
                autoCleanupSourceBuffer: true,
            }
        );

        attachPlayerEvents(player, streamUrl);
        player.attachMediaElement(videoElement);
        player.load();

        try {
            await player.play();
            setStatus(`正在播放：${streamUrl}`, 'ok');
        } catch (error) {
            setStatus(`已连接流，但自动播放失败：${error.message}。请手动点击视频区域继续播放。`, 'error');
        }
    }

    function open(url, taskName) {
        setModalVisible(true);
        titleLabel.textContent = taskName ? `当前任务：${taskName}` : '当前任务视频流';

        Promise.resolve()
            .then(function () {
                return play(url);
            })
            .catch(function (error) {
                currentUrlElement.textContent = String(url || '未提供视频流地址');
                setStatus(error.message || '播放失败。', 'error');
            });
    }

    function close() {
        stopPlayback();
        currentUrl = '';
        currentUrlElement.textContent = '未选择视频流';
        titleLabel.textContent = '点击视频URL后自动开始播放。';
        setModalVisible(false);
    }

    closeButton.addEventListener('click', close);
    stopButton.addEventListener('click', stopPlayback);
    replayButton.addEventListener('click', function () {
        if (!currentUrl) {
            setStatus('当前没有可重新播放的视频流。', 'error');
            return;
        }

        play(currentUrl).catch(function (error) {
            setStatus(error.message || '重新播放失败。', 'error');
        });
    });

    modal.addEventListener('click', function (event) {
        if (event.target === modal) {
            close();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && modal.classList.contains('show')) {
            close();
        }
    });

    setSupportState();

    window.managerStreamPlayer = {
        open: open,
        close: close,
        stop: stopPlayback,
    };
})(window, document);