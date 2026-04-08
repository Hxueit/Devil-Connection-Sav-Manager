"""缓存清理脚本常量

定义所有缓存清理相关的 JavaScript 脚本。
"""
from typing import Dict, Any

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

CLEANUP_SCRIPTS = {
    "cache_tmp": {
        "name": "cache_tmp",
        "script": """(function() {
            try {
                const elements = document.querySelectorAll('.__cache_tmp');
                const count = elements.length;
                elements.forEach(el => el.remove());
                return { success: true, count: count };
            } catch (e) {
                return { success: false, error: e.toString() };
            }
        })()""",
        "safe": True
    },
    
    "bg_loop_old": {
        "name": "bg_loop_old",
        "script": """(function() {
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
        "safe": True
    },
    
    "tap_effect": {
        "name": "tap_effect",
        "script": """(function() {
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
        "safe": True
    },
    
    "snap_modal": {
        "name": "snap_modal",
        "script": """(function() {
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
        "safe": True
    },
    
    "reflection_empty": {
        "name": "reflection_empty",
        "script": """(function() {
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
        "safe": True
    },
    
    "photo_assets": {
        "name": "photo_assets",
        "script": """(function() {
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
        "safe": False,
        "risky": True,
        "requires_photo_closed": True
    },
    
    "opacity_zero_images": {
        "name": "opacity_zero_images",
        "script": """(function() {
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
        "safe": False,
        "risky": True
    },
    
    "display_none_layers": {
        "name": "display_none_layers",
        "script": """(function() {
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
        "safe": False,
        "risky": True
    },
    
    "hidden_videos": {
        "name": "hidden_videos",
        "script": """(function() {
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
        "safe": False,
        "risky": True
    },
    
    "message_layer_content": {
        "name": "message_layer_content",
        "script": """(function() {
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
        "safe": False,
        "risky": True
    },
    
}

JS_SCAN_DANGEROUS_ITEMS = """(function() {
    const found = [];
    
    const checks = [
        { type: 'selector', name: '.fixlayer', selector: '.fixlayer' },
        { type: 'selector', name: '.layer_fix *', selector: '.layer_fix *' },
        { type: 'selector', name: '.tyrano_chara', selector: '.tyrano_chara' },
        { type: 'selector', name: '.event-setting-element', selector: '.event-setting-element' },
        { type: 'selector', name: '.layer_menu', selector: '.layer_menu' },
        { type: 'selector', name: '.glink_button', selector: '.glink_button' },
        { type: 'selector', name: '.button_graphic', selector: '.button_graphic' },
        { type: 'selector', name: '.message_inner', selector: '.message_inner' },
        { type: 'selector', name: '.menu_button.event-setting-element', selector: '.menu_button.event-setting-element' },
        { type: 'selector', name: '.skip_button.event-setting-element', selector: '.skip_button.event-setting-element' },
        { type: 'selector', name: '.log_button.event-setting-element', selector: '.log_button.event-setting-element' },
        { type: 'selector', name: '#bgmovie', selector: '#bgmovie' },
        { type: 'selector', name: '.bg_loop', selector: '.bg_loop' },
        { type: 'selector', name: '.title_movie', selector: '.title_movie' },
        { type: 'selector', name: '#fgmovie', selector: '#fgmovie' },
        { type: 'selector', name: '#deco_canvas', selector: '#deco_canvas' },
        { type: 'selector', name: '#deco_menu', selector: '#deco_menu' },
        { type: 'selector', name: '.photo_chara', selector: '.photo_chara' },
        { type: 'selector', name: '.photo_pose', selector: '.photo_pose' },
        { type: 'selector', name: '.photo_effect', selector: '.photo_effect' },
        { type: 'selector', name: '.snap_modal:visible', selector: '.snap_modal:visible' },
        { type: 'selector', name: '.body_bg', selector: '.body_bg' },
        { type: 'selector', name: '.reflection:not(:empty)', selector: '.reflection:not(:empty)' },
        { type: 'selector', name: '.animated', selector: '.animated' },
        { type: 'selector', name: '[l_visible="true"] *', selector: '[l_visible="true"] *' },
        { type: 'selector', name: '.base img, .layer_base img', selector: '.base img, .layer_base img' },
        
        { type: 'property', name: 'TYRANO.kag.layer.map_layer_fore', path: ['TYRANO', 'kag', 'layer', 'map_layer_fore'] },
        { type: 'property', name: 'TYRANO.kag.layer.map_layer_back', path: ['TYRANO', 'kag', 'layer', 'map_layer_back'] },
        { type: 'property', name: 'TYRANO.kag.stat.current_bgm', path: ['TYRANO', 'kag', 'stat', 'current_bgm'] },
        { type: 'property', name: 'TYRANO.kag.stat.current_se', path: ['TYRANO', 'kag', 'stat', 'current_se'] },
        { type: 'property', name: 'TYRANO.kag.stat.current_bgmovie', path: ['TYRANO', 'kag', 'stat', 'current_bgmovie'] },
        { type: 'property', name: 'TYRANO.kag.stat.current_bgmovie.storage', path: ['TYRANO', 'kag', 'stat', 'current_bgmovie', 'storage'] },
        { type: 'property', name: 'TYRANO.kag.tmp.video_playing', path: ['TYRANO', 'kag', 'tmp', 'video_playing'] },
        { type: 'property', name: 'TYRANO.kag.stat.current_camera', path: ['TYRANO', 'kag', 'stat', 'current_camera'] },
        { type: 'property', name: 'TYRANO.kag.stat.f', path: ['TYRANO', 'kag', 'stat', 'f'] },
        { type: 'property', name: 'TYRANO.kag.stat.map_label', path: ['TYRANO', 'kag', 'stat', 'map_label'] },
        { type: 'property', name: 'TYRANO.kag.stat.map_macro', path: ['TYRANO', 'kag', 'stat', 'map_macro'] },
        { type: 'property', name: 'TYRANO.kag.tmp.audio_context', path: ['TYRANO', 'kag', 'tmp', 'audio_context'] },
        { type: 'property', name: 'TYRANO.kag.tmp.map_bgm', path: ['TYRANO', 'kag', 'tmp', 'map_bgm'] },
        { type: 'property', name: 'TYRANO.kag.tmp.map_se', path: ['TYRANO', 'kag', 'tmp', 'map_se'] },
        { type: 'property', name: 'TYRANO.kag.stat.bg_layermode.animations', path: ['TYRANO', 'kag', 'stat', 'bg_layermode', 'animations'] },
        
        { type: 'function', name: "TYRANO.kag.layer.getLayer('fix')", func: 'TYRANO.kag.layer.getLayer', args: ['fix'], check: 'typeof TYRANO.kag.layer.getLayer === "function"' },
        { type: 'function', name: "TYRANO.kag.layer.getLayer('base', 'fore')", func: 'TYRANO.kag.layer.getLayer', args: ['base', 'fore'], check: 'typeof TYRANO.kag.layer.getLayer === "function"' },
        { type: 'function', name: "TYRANO.kag.layer.getMenuLayer()", func: 'TYRANO.kag.layer.getMenuLayer', args: [], check: 'typeof TYRANO.kag.layer.getMenuLayer === "function"' },
        
        { type: 'jquery', name: ':animated (jQuery)', selector: ':animated', check: 'typeof $ !== "undefined"' }
    ];
    
    checks.forEach(item => {
        if (item.type === 'selector') {
            try {
                const elements = document.querySelectorAll(item.selector);
                if (elements.length > 0) {
                    found.push({
                        name: item.name,
                        type: 'selector',
                        selector: item.selector,
                        count: elements.length
                    });
                }
            } catch (e) {
            }
        } else if (item.type === 'property') {
            try {
                let obj = window;
                let exists = true;
                for (let i = 0; i < item.path.length; i++) {
                    const key = item.path[i];
                    if (obj[key] === undefined || obj[key] === null) {
                        exists = false;
                        break;
                    }
                    obj = obj[key];
                }
                
                if (exists && obj !== null && obj !== undefined) {
                    found.push({
                        name: item.name,
                        type: 'property',
                        path: item.path.join('.')
                    });
                }
            } catch (e) {
            }
        } else if (item.type === 'function') {
            try {
                if (item.check && !eval(item.check)) {
                    return;
                }
                
                const funcPath = item.func.split('.');
                let funcObj = window;
                for (let i = 0; i < funcPath.length; i++) {
                    funcObj = funcObj[funcPath[i]];
                    if (funcObj === undefined || funcObj === null) {
                        return;
                    }
                }
                
                if (typeof funcObj === 'function') {
                    try {
                        const result = funcObj.apply(null, item.args);
                        if (result !== null && result !== undefined) {
                            found.push({
                                name: item.name,
                                type: 'function',
                                func: item.func,
                                args: item.args
                            });
                        }
                    } catch (e) {
                        found.push({
                            name: item.name,
                            type: 'function',
                            func: item.func,
                            args: item.args
                        });
                    }
                }
            } catch (e) {
                // 忽略错误
            }
        } else if (item.type === 'jquery') {
            try {
                if (item.check && eval(item.check)) {
                    const elements = $(item.selector);
                    if (elements.length > 0) {
                        found.push({
                            name: item.name,
                            type: 'jquery',
                            selector: item.selector,
                            count: elements.length
                        });
                    }
                }
            } catch (e) {
                // 忽略错误
            }
        }
    });
    
    return found;
})()"""


def generate_cleanup_script(item_info: Dict[str, Any]) -> str:
    """根据发现的项动态生成清理脚本
    
    Args:
        item_info: 扫描结果项，包含 name, type, 和其他类型特定字段
        
    Returns:
        清理脚本字符串
    """
    item_type = item_info.get('type')
    item_name = item_info.get('name', '')
    
    if item_type == 'selector':
        selector = item_info.get('selector', '')
        # 转义单引号
        selector_escaped = selector.replace("'", "\\'")
        return f"""(function() {{
            try {{
                const elements = document.querySelectorAll('{selector_escaped}');
                let count = elements.length;
                elements.forEach(el => el.remove());
                return {{ success: true, count: count }};
            }} catch (e) {{
                return {{ success: false, error: e.toString() }};
            }}
        }})()"""
    
    elif item_type == 'property':
        path = item_info.get('path', '')
        parts = path.split('.')
        if len(parts) < 2:
            return ""
        
        return f"""(function() {{
            try {{
                const path = '{path}';
                const parts = path.split('.');
                let obj = window;
                for (let i = 0; i < parts.length - 1; i++) {{
                    if (obj[parts[i]] === undefined || obj[parts[i]] === null) {{
                        return {{ success: false, error: 'Path not found: ' + parts.slice(0, i + 1).join('.') }};
                    }}
                    obj = obj[parts[i]];
                }}
                const lastKey = parts[parts.length - 1];
                if (typeof obj[lastKey] === 'object' && obj[lastKey] !== null && !Array.isArray(obj[lastKey])) {{
                    obj[lastKey] = {{}};
                }} else {{
                    obj[lastKey] = null;
                }}
                return {{ success: true, count: 1 }};
            }} catch (e) {{
                return {{ success: false, error: e.toString() }};
            }}
        }})()"""
    
    elif item_type == 'function':
        func_path = item_info.get('func', '')
        args = item_info.get('args', [])
        args_str: str = ', '.join([f"'{arg}'" if isinstance(arg, str) else str(arg) for arg in args])
        
        return f"""(function() {{
            try {{
                const funcPath = '{func_path}'.split('.');
                let funcObj = window;
                for (let i = 0; i < funcPath.length; i++) {{
                    funcObj = funcObj[funcPath[i]];
                }}
                if (typeof funcObj !== 'function') {{
                    return {{ success: false, error: 'Function not found' }};
                }}
                const result = funcObj({args_str});
                if (result && typeof result.innerHTML !== 'undefined') {{
                    result.innerHTML = '';
                    return {{ success: true, count: 1 }};
                }} else if (result && result.remove) {{
                    result.remove();
                    return {{ success: true, count: 1 }};
                }}
                return {{ success: true, count: 0 }};
            }} catch (e) {{
                return {{ success: false, error: e.toString() }};
            }}
        }})()"""
    
    elif item_type == 'jquery':
        selector = item_info.get('selector', '')
        selector_escaped = selector.replace("'", "\\'")
        return f"""(function() {{
            try {{
                if (typeof $ === 'undefined') {{
                    return {{ success: false, error: 'jQuery not available' }};
                }}
                const elements = $('{selector_escaped}');
                let count = elements.length;
                elements.remove();
                return {{ success: true, count: count }};
            }} catch (e) {{
                return {{ success: false, error: e.toString() }};
            }}
        }})()"""
    
    return ""


SAFE_CLEANUP_ITEMS = [
    "cache_tmp",
    "bg_loop_old",
    "tap_effect",
    "snap_modal",
    "reflection_empty"
]


RISKY_CLEANUP_ITEMS = [
    "photo_assets",
    "opacity_zero_images",
    "display_none_layers",
    "hidden_videos",
    "message_layer_content"
]

