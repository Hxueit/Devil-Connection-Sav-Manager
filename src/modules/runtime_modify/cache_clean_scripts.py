"""缓存清理用到的 JavaScript 脚本

游戏长时间运行后，页面里会残留大量不再使用的元素/视频/图片，导致卡顿。
每个清理脚本返回 { success, count } 或 { success: false, error }。
"""
import json
from typing import Any, Dict

JS_CHECK_STATE = """(function() {
    try {
        if (typeof TYRANO === 'undefined' || !TYRANO.kag || !TYRANO.kag.stat) {
            return { canClean: false, reason: 'TYRANO not available' };
        }
        const stat = TYRANO.kag.stat;
        const canClean = !stat.is_trans && !stat.is_wait_anim;
        return {
            canClean: canClean,
            is_trans: stat.is_trans,
            is_wait_anim: stat.is_wait_anim,
            is_wait: stat.is_wait,
            is_stop: stat.is_stop
        };
    } catch (e) {
        return { canClean: false, reason: e.toString() };
    }
})()"""

JS_CHECK_PHOTO_OPEN = """(function() {
    try {
        const photoModal = document.querySelector('.snap_modal:not([style*="display: none"])');
        const photoChara = document.querySelector('.photo_chara');
        const photoPose = document.querySelector('.photo_pose');
        const photoEffect = document.querySelector('.photo_effect');
        return {
            isOpen: !!(photoModal || photoChara || photoPose || photoEffect)
        };
    } catch (e) {
        return { isOpen: false, error: e.toString() };
    }
})()"""

# 安全项：只移除游戏已经不再使用的元素
SAFE_CLEANUP_SCRIPTS = {
    "cache_tmp": """(function() {
    try {
        const elements = document.querySelectorAll('.__cache_tmp');
        const count = elements.length;
        elements.forEach(el => el.remove());
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "bg_loop_old": """(function() {
    try {
        const videos = document.querySelectorAll('.bg_loop.old');
        let count = 0;
        videos.forEach(video => {
            if (video.tagName === 'VIDEO') {
                video.pause();
                video.src = '';
                video.load();
            }
            video.remove();
            count++;
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "tap_effect": """(function() {
    try {
        const container = document.querySelector('.tap_effect');
        if (!container) {
            return { success: true, count: 0 };
        }
        const children = Array.from(container.children);
        let count = 0;
        children.forEach(child => {
            const style = window.getComputedStyle(child);
            const animationState = style.animationPlayState;
            if (animationState === 'paused' || animationState === '') {
                child.remove();
                count++;
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "snap_modal": """(function() {
    try {
        const modals = document.querySelectorAll('.snap_modal');
        let count = 0;
        modals.forEach(modal => {
            const style = window.getComputedStyle(modal);
            if (style.display === 'none') {
                modal.remove();
                count++;
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "reflection_empty": """(function() {
    try {
        const reflections = document.querySelectorAll('.reflection');
        let count = 0;
        reflections.forEach(reflection => {
            if (reflection.children.length === 0) {
                reflection.remove();
                count++;
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",
}

# 有风险项：可能影响当前画面，默认不勾选
RISKY_CLEANUP_SCRIPTS = {
    "photo_assets": """(function() {
    try {
        if (typeof TYRANO === 'undefined' || !TYRANO.kag || !TYRANO.kag.dc) {
            return { success: false, error: 'TYRANO.kag.dc not available' };
        }
        
        const dc = TYRANO.kag.dc;
        let revokedCount = 0;
        
        if (dc.photoAssets) {
            Object.keys(dc.photoAssets).forEach(key => {
                const asset = dc.photoAssets[key];
                if (asset && asset.frames) {
                    asset.frames.forEach(frame => {
                        if (frame && frame.imageElement && frame.imageElement.src) {
                            try {
                                if (frame.imageElement.src.startsWith('blob:')) {
                                    URL.revokeObjectURL(frame.imageElement.src);
                                    revokedCount++;
                                }
                            } catch (e) {
                            }
                        }
                    });
                }
            });
            dc.photoAssets = {};
        }
        
        if (dc.playingCharas && Array.isArray(dc.playingCharas)) {
            dc.playingCharas.forEach(player => {
                if (player && typeof player.stop === 'function') {
                    try {
                        player.stop();
                    } catch (e) {
                    }
                }
            });
            dc.playingCharas = [];
        }
        
        return { success: true, count: revokedCount };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "opacity_zero_images": """(function() {
    try {
        const stat = TYRANO.kag.stat;
        if (stat.is_trans) {
            return { success: false, error: 'is_trans is true, skipping' };
        }
        const images = document.querySelectorAll('img, .layer img');
        let count = 0;
        images.forEach(img => {
            const style = window.getComputedStyle(img);
            if (style.opacity === '0') {
                const $el = $(img);
                if (!$el.is(':animated') && !img.classList.contains('animated')) {
                    const layer = $el.closest('[l_visible]');
                    if (layer.length === 0 || layer.attr('l_visible') === 'false') {
                        img.remove();
                        count++;
                    }
                }
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "display_none_layers": """(function() {
    try {
        const stat = TYRANO.kag.stat;
        if (stat.is_trans) {
            return { success: false, error: 'is_trans is true, skipping' };
        }
        const layers = document.querySelectorAll('[class*="layer"]:not(.layer_menu):not(.layer_free)');
        let count = 0;
        layers.forEach(layer => {
            const style = window.getComputedStyle(layer);
            if (style.display === 'none') {
                if (!layer.classList.contains('animated')) {
                    if (!layer.classList.contains('base')) {
                        const children = layer.querySelectorAll('img, video');
                        children.forEach(child => {
                            child.remove();
                            count++;
                        });
                    }
                }
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "hidden_videos": """(function() {
    try {
        const videos = document.querySelectorAll('video');
        let count = 0;
        const currentBgMovie = TYRANO.kag.stat.current_bgmovie?.storage || '';
        videos.forEach(video => {
            const style = window.getComputedStyle(video);
            if (style.display === 'none' && style.opacity === '0') {
                if (video.paused && (video.ended || video.currentTime === 0)) {
                    const src = video.src || '';
                    if (!currentBgMovie || !src.includes(currentBgMovie)) {
                        video.pause();
                        video.src = '';
                        video.load();
                        video.remove();
                        count++;
                    }
                }
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",

    "message_layer_content": """(function() {
    try {
        const messageInners = document.querySelectorAll('.message_inner');
        let count = 0;
        messageInners.forEach(inner => {
            const style = window.getComputedStyle(inner);
            if (style.display === 'none' && inner.textContent.trim() === '') {
                inner.innerHTML = '';
                count++;
            }
        });
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""",
}

# 照片界面打开时清理这些项会弄坏照片界面，必须跳过
REQUIRES_PHOTO_CLOSED = {"photo_assets"}

# 「全部」分组：扫描页面里存在的元素/属性/函数，由用户自行决定是否清理（很可能弄坏游戏）
JS_SCAN_DANGEROUS_ITEMS = """(function() {
    const found = [];
    const lookup = path => path.reduce((obj, key) => (obj === undefined || obj === null) ? undefined : obj[key], window);

    const selectors = [
        '.fixlayer', '.layer_fix *', '.tyrano_chara', '.event-setting-element', '.layer_menu',
        '.glink_button', '.button_graphic', '.message_inner', '.menu_button.event-setting-element',
        '.skip_button.event-setting-element', '.log_button.event-setting-element', '#bgmovie', '.bg_loop',
        '.title_movie', '#fgmovie', '#deco_canvas', '#deco_menu', '.photo_chara', '.photo_pose',
        '.photo_effect', '.snap_modal:visible', '.body_bg', '.reflection:not(:empty)', '.animated',
        '[l_visible="true"] *', '.base img, .layer_base img'
    ];
    selectors.forEach(selector => {
        try {
            const count = document.querySelectorAll(selector).length;
            if (count > 0) {
                found.push({ name: selector, type: 'selector', selector: selector, count: count });
            }
        } catch (e) {
        }
    });

    const properties = [
        'TYRANO.kag.layer.map_layer_fore', 'TYRANO.kag.layer.map_layer_back',
        'TYRANO.kag.stat.current_bgm', 'TYRANO.kag.stat.current_se', 'TYRANO.kag.stat.current_bgmovie',
        'TYRANO.kag.stat.current_bgmovie.storage', 'TYRANO.kag.tmp.video_playing',
        'TYRANO.kag.stat.current_camera', 'TYRANO.kag.stat.f', 'TYRANO.kag.stat.map_label',
        'TYRANO.kag.stat.map_macro', 'TYRANO.kag.tmp.audio_context', 'TYRANO.kag.tmp.map_bgm',
        'TYRANO.kag.tmp.map_se', 'TYRANO.kag.stat.bg_layermode.animations'
    ];
    properties.forEach(path => {
        try {
            const value = lookup(path.split('.'));
            if (value !== undefined && value !== null) {
                found.push({ name: path, type: 'property', path: path });
            }
        } catch (e) {
        }
    });

    const functions = [
        { name: "TYRANO.kag.layer.getLayer('fix')", func: 'TYRANO.kag.layer.getLayer', args: ['fix'] },
        { name: "TYRANO.kag.layer.getLayer('base', 'fore')", func: 'TYRANO.kag.layer.getLayer', args: ['base', 'fore'] },
        { name: "TYRANO.kag.layer.getMenuLayer()", func: 'TYRANO.kag.layer.getMenuLayer', args: [] }
    ];
    functions.forEach(item => {
        let fn;
        try {
            fn = lookup(item.func.split('.'));
        } catch (e) {
            return;
        }
        if (typeof fn !== 'function') {
            return;
        }
        let result;
        try {
            result = fn.apply(null, item.args);
        } catch (e) {
            result = true;  // 调用出错也列出来，交给用户判断
        }
        if (result !== null && result !== undefined) {
            found.push({ name: item.name, type: 'function', func: item.func, args: item.args });
        }
    });

    try {
        const count = typeof $ !== 'undefined' ? $(':animated').length : 0;
        if (count > 0) {
            found.push({ name: ':animated (jQuery)', type: 'jquery', selector: ':animated', count: count });
        }
    } catch (e) {
    }

    return found;
})()"""


def generate_cleanup_script(item: Dict[str, Any]) -> str:
    """为扫描结果中的一项生成清理脚本；无法处理时返回空字符串"""
    item_type = item.get("type")
    # 用 json.dumps 把 Python 值变成 JS 字面量，自动处理引号转义
    if item_type == "selector":
        return """(function() {
    try {
        const elements = document.querySelectorAll(%s);
        const count = elements.length;
        elements.forEach(el => el.remove());
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""" % json.dumps(item.get("selector", ""))

    if item_type == "property":
        path = item.get("path", "")
        if "." not in path:
            return ""
        # 对象清空为 {}，其它值置为 null
        return """(function() {
    try {
        const parts = %s.split('.');
        let obj = window;
        for (let i = 0; i < parts.length - 1; i++) {
            if (obj[parts[i]] === undefined || obj[parts[i]] === null) {
                return { success: false, error: 'Path not found: ' + parts.slice(0, i + 1).join('.') };
            }
            obj = obj[parts[i]];
        }
        const lastKey = parts[parts.length - 1];
        if (typeof obj[lastKey] === 'object' && obj[lastKey] !== null && !Array.isArray(obj[lastKey])) {
            obj[lastKey] = {};
        } else {
            obj[lastKey] = null;
        }
        return { success: true, count: 1 };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""" % json.dumps(path)

    if item_type == "function":
        # 调用函数拿到元素：能清空内容就清空，否则移除
        return """(function() {
    try {
        let fn = window;
        %s.split('.').forEach(key => { fn = fn[key]; });
        if (typeof fn !== 'function') {
            return { success: false, error: 'Function not found' };
        }
        const result = fn(...%s);
        if (result && typeof result.innerHTML !== 'undefined') {
            result.innerHTML = '';
            return { success: true, count: 1 };
        } else if (result && result.remove) {
            result.remove();
            return { success: true, count: 1 };
        }
        return { success: true, count: 0 };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""" % (json.dumps(item.get("func", "")), json.dumps(item.get("args", [])))

    if item_type == "jquery":
        return """(function() {
    try {
        if (typeof $ === 'undefined') {
            return { success: false, error: 'jQuery not available' };
        }
        const elements = $(%s);
        const count = elements.length;
        elements.remove();
        return { success: true, count: count };
    } catch (e) {
        return { success: false, error: e.toString() };
    }
})()""" % json.dumps(item.get("selector", ""))

    return ""
