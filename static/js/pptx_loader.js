/**
 * PptxLoader — Client-side PPTX Parser for Zentrol
 * Extracts slide text and renders slides as images entirely in the browser.
 * Layout is approximate (canvas + OOXML positions): not identical to PowerPoint.
 * Local Docker/VM uploads use LibreOffice+PDF for pixel-accurate slides.
 *
 * Dependencies: JSZip (loaded via CDN)
 * @version 1.0.0
 */

class PptxLoader {
    constructor(options = {}) {
        this.options = {
            debug: options.debug ?? false,
            onProgress: options.onProgress ?? null,   // (pct, message) => {}
            onSlideReady: options.onSlideReady ?? null // (index, {imageUrl, text}) => {}
        };

        this.slides = [];       // [{imageUrl, text, notes}]
        this.fileName = '';
        this.isLoaded = false;
        /** Native slide size from ppt/presentation.xml (EMU). Defaults to 16:9. */
        this.slideCxEmu = 9144000;
        this.slideCyEmu = 5143500;
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Load a PPTX File object and parse it.
     * @param {File} file
     * @returns {Promise<Array>} slides array
     */
    async load(file) {
        if (!file) throw new Error('No file provided');

        const ext = file.name.split('.').pop().toLowerCase();
        if (!['pptx', 'ppt'].includes(ext)) {
            throw new Error('Please upload a .pptx or .ppt file');
        }

        this.fileName = file.name;
        this.slides = [];
        this.isLoaded = false;

        this._progress(5, 'Reading file…');

        const arrayBuffer = await this._readFile(file);

        this._progress(15, 'Unzipping PPTX…');
        const zip = await this._unzip(arrayBuffer);

        await this._readSlideDimensions(zip);

        this._progress(25, 'Parsing slide structure…');
        const slideCount = this._countSlides(zip);

        if (slideCount === 0) {
            throw new Error('No slides found in this file. Please check it is a valid PPTX.');
        }

        this._log(`Found ${slideCount} slides`);

        // Parse each slide
        for (let i = 1; i <= slideCount; i++) {
            const pct = 25 + Math.round(((i - 1) / slideCount) * 65);
            this._progress(pct, `Extracting slide ${i} of ${slideCount}…`);

            const slideData = await this._parseSlide(zip, i);
            this.slides.push(slideData);

            if (typeof this.options.onSlideReady === 'function') {
                this.options.onSlideReady(i - 1, slideData);
            }
        }

        this._progress(95, 'Finalising…');
        this.isLoaded = true;
        this._progress(100, 'Done!');

        this._log(`Loaded ${this.slides.length} slides from "${file.name}"`);
        return this.slides;
    }

    /**
     * Get all slides.
     * @returns {Array<{imageUrl:string|null, text:string, notes:string}>}
     */
    getSlides() {
        return this.slides;
    }

    /**
     * Get text for a specific slide (0-based index).
     */
    getSlideText(index) {
        return this.slides[index]?.text ?? '';
    }

    // -------------------------------------------------------------------------
    // Internal: File Reading
    // -------------------------------------------------------------------------

    _readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsArrayBuffer(file);
        });
    }

    async _unzip(arrayBuffer) {
        if (typeof JSZip === 'undefined') {
            throw new Error('JSZip is not loaded. Please include it before pptx_loader.js.');
        }
        return await JSZip.loadAsync(arrayBuffer);
    }

    /**
     * Read slide width/height in EMU from presentation.xml (varies 16:9, 4:3, widescreen).
     * Wrong defaults distort text and clip pictures vs PowerPoint.
     */
    async _readSlideDimensions(zip) {
        this.slideCxEmu = 9144000;
        this.slideCyEmu = 5143500;
        const presFile = zip.files['ppt/presentation.xml'];
        if (!presFile) return;
        try {
            const xmlStr = await presFile.async('string');
            const doc = new DOMParser().parseFromString(xmlStr, 'text/xml');
            const elements = doc.getElementsByTagName('*');
            for (let i = 0; i < elements.length; i++) {
                const el = elements[i];
                if (el.localName === 'sldSz') {
                    const cx = parseInt(el.getAttribute('cx'), 10);
                    const cy = parseInt(el.getAttribute('cy'), 10);
                    if (cx > 0 && cy > 0) {
                        this.slideCxEmu = cx;
                        this.slideCyEmu = cy;
                    }
                    break;
                }
            }
        } catch (e) {
            this._log('warn', `Slide dimensions fallback: ${e.message}`);
        }
    }

    /**
     * Scale picture draw rect so it fits in the canvas (avoids clipped logos at bottom).
     * @returns {{dx:number,dy:number,dw:number,dh:number}|null}
     */
    _clampImageRect(canvasW, canvasH, x, y, w, h) {
        let dx = Math.round(x);
        let dy = Math.round(y);
        let dw = Math.round(w);
        let dh = Math.round(h);
        if (!Number.isFinite(dw) || !Number.isFinite(dh) || dw <= 0 || dh <= 0) return null;
        if (dx >= canvasW || dy >= canvasH) return null;
        const scale = Math.min(1, (canvasW - dx) / dw, (canvasH - dy) / dh);
        dw = Math.round(dw * scale);
        dh = Math.round(dh * scale);
        if (dw < 2 || dh < 2) return null;
        return { dx, dy, dw, dh };
    }

    // -------------------------------------------------------------------------
    // Internal: Slide Parsing
    // -------------------------------------------------------------------------

    _countSlides(zip) {
        let count = 0;
        while (zip.files[`ppt/slides/slide${count + 1}.xml`]) {
            count++;
        }
        return count;
    }

    async _parseSlide(zip, slideNumber) {
        const slideXmlPath = `ppt/slides/slide${slideNumber}.xml`;
        const slideXmlFile = zip.files[slideXmlPath];
        if (!slideXmlFile) return { imageUrl: null, text: '', notes: '' };

        const xmlStr = await slideXmlFile.async('string');
        const text = this._extractText(xmlStr);
        const notes = await this._extractNotes(zip, slideNumber);
        const imageUrl = await this._renderSlide(zip, slideNumber, xmlStr, text);

        return { imageUrl, text, notes };
    }

    /**
     * Extract all visible text from slide XML.
     * Handles <a:t> text nodes, preserving paragraph breaks.
     */
    _extractText(xmlStr) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlStr, 'text/xml');

        // Collect all <a:t> elements (DrawingML text runs)
        const textNodes = doc.getElementsByTagNameNS(
            'http://schemas.openxmlformats.org/drawingml/2006/main', 't'
        );

        const paragraphNodes = doc.getElementsByTagNameNS(
            'http://schemas.openxmlformats.org/drawingml/2006/main', 'p'
        );

        // Build text paragraph by paragraph for natural TTS flow
        const paragraphs = [];
        for (const para of paragraphNodes) {
            const runs = para.getElementsByTagNameNS(
                'http://schemas.openxmlformats.org/drawingml/2006/main', 't'
            );
            const line = Array.from(runs).map(r => r.textContent).join('').trim();
            if (line) paragraphs.push(line);
        }

        return paragraphs.join('. ');
    }

    /**
     * Extract speaker notes from notesSlide XML.
     */
    async _extractNotes(zip, slideNumber) {
        const notesPath = `ppt/notesSlides/notesSlide${slideNumber}.xml`;
        const notesFile = zip.files[notesPath];
        if (!notesFile) return '';

        const xmlStr = await notesFile.async('string');
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlStr, 'text/xml');

        const textNodes = doc.getElementsByTagNameNS(
            'http://schemas.openxmlformats.org/drawingml/2006/main', 't'
        );
        return Array.from(textNodes).map(n => n.textContent).join(' ').trim();
    }

    /**
     * Render a slide to a canvas and return a data URL.
     * This creates a visual representation using slide text + background.
     * For full fidelity rendering, a server-side converter would be needed,
     * but this gives a clean readable version for browser-only use.
     */
    async _renderSlide(zip, slideNumber, xmlStr, text) {
        // Try to extract background color
        const bgColor = this._extractBgColor(xmlStr);

        const canvasW = 960;
        const canvasH = Math.max(
            360,
            Math.round((canvasW * this.slideCyEmu) / this.slideCxEmu),
        );

        // Try to extract embedded images (coordinates match slide aspect ratio)
        const images = await this._extractSlideImages(zip, slideNumber, xmlStr, canvasW, canvasH);

        // Render to canvas
        const canvas = document.createElement('canvas');
        canvas.width = canvasW;
        canvas.height = canvasH;
        const ctx = canvas.getContext('2d');

        // Background
        ctx.fillStyle = bgColor || '#FFFFFF';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // If there's a background image, draw it first
        if (images.background) {
            try {
                await this._drawImage(ctx, images.background, 0, 0, canvas.width, canvas.height);
            } catch (e) { /* skip */ }
        }

        // Draw slide number badge
        ctx.fillStyle = 'rgba(15, 30, 46, 0.08)';
        ctx.beginPath();
        ctx.roundRect(20, 20, 56, 32, 8);
        ctx.fill();
        ctx.fillStyle = '#0F1E2E';
        ctx.font = '600 13px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`Slide ${slideNumber}`, 32, 41);

        // Parse and draw text shapes
        await this._drawTextShapes(ctx, xmlStr, canvas.width, canvas.height);

        // Draw inline images (scale down if OOXML box overflows canvas — fixes clipped logos)
        for (const img of images.inline) {
            try {
                const box = this._clampImageRect(canvas.width, canvas.height, img.x, img.y, img.w, img.h);
                if (!box) continue;
                await this._drawImage(ctx, img.data, box.dx, box.dy, box.dw, box.dh);
            } catch (e) { /* skip */ }
        }

        return canvas.toDataURL('image/png');
    }

    _extractBgColor(xmlStr) {
        // Look for solidFill in background
        const match = xmlStr.match(/<p:bg>.*?<a:srgbClr val="([0-9A-Fa-f]{6})".*?<\/p:bg>/s);
        if (match) return `#${match[1]}`;

        // Common theme backgrounds
        const schemeMatch = xmlStr.match(/<p:bg>.*?<a:schemeClr val="([^"]+)".*?<\/p:bg>/s);
        return null;
    }

    async _extractSlideImages(zip, slideNumber, xmlStr, canvasW, canvasH) {
        const result = { background: null, inline: [] };

        try {
            // Find relationship file
            const relsPath = `ppt/slides/_rels/slide${slideNumber}.xml.rels`;
            const relsFile = zip.files[relsPath];
            if (!relsFile) return result;

            const relsXml = await relsFile.async('string');
            const parser = new DOMParser();
            const relsDoc = parser.parseFromString(relsXml, 'text/xml');
            const rels = relsDoc.getElementsByTagName('Relationship');

            // Build rId → image path map
            const imgMap = {};
            for (const rel of rels) {
                const type = rel.getAttribute('Type') || '';
                if (type.includes('image')) {
                    const rId = rel.getAttribute('Id');
                    let target = rel.getAttribute('Target');
                    if (!target.startsWith('ppt/')) {
                        target = `ppt/slides/${target}`.replace('/slides/../', '/');
                    }
                    imgMap[rId] = target;
                }
            }

            // Parse blipFill references from slide XML
            const slideParser = new DOMParser();
            const slideDoc = slideParser.parseFromString(xmlStr, 'text/xml');

            // Background image
            const bgBlip = slideDoc.querySelector('bg blipFill blip');
            if (bgBlip) {
                const rId = bgBlip.getAttributeNS(
                    'http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'embed'
                );
                if (rId && imgMap[rId]) {
                    const imgFile = zip.files[imgMap[rId]];
                    if (imgFile) {
                        const b64 = await imgFile.async('base64');
                        const ext = imgMap[rId].split('.').pop().toLowerCase();
                        result.background = `data:image/${ext === 'jpg' ? 'jpeg' : ext};base64,${b64}`;
                    }
                }
            }

            // Inline images (pic elements)
            // Also check drawing namespace
            const allPics = [
                ...Array.from(slideDoc.getElementsByTagName('p:pic')),
                ...Array.from(slideDoc.getElementsByTagName('pic:pic'))
            ];

            for (const pic of allPics) {
                const blip = pic.querySelector('blipFill blip') ||
                             pic.getElementsByTagNameNS(
                                 'http://schemas.openxmlformats.org/drawingml/2006/main', 'blip'
                             )[0];
                if (!blip) continue;

                const rId = blip.getAttributeNS(
                    'http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'embed'
                );
                if (!rId || !imgMap[rId]) continue;

                // Get position/size from spPr/xfrm
                const xfrm = pic.querySelector('spPr xfrm') ||
                             pic.getElementsByTagNameNS(
                                 'http://schemas.openxmlformats.org/drawingml/2006/main', 'xfrm'
                             )[0];

                let x = 0, y = 0, w = canvasW, h = canvasH;
                if (xfrm) {
                    const off = xfrm.querySelector('off') ||
                               xfrm.getElementsByTagNameNS(
                                   'http://schemas.openxmlformats.org/drawingml/2006/main', 'off'
                               )[0];
                    const ext = xfrm.querySelector('ext') ||
                               xfrm.getElementsByTagNameNS(
                                   'http://schemas.openxmlformats.org/drawingml/2006/main', 'ext'
                               )[0];

                    if (off) {
                        const ox = parseInt(off.getAttribute('x'), 10) || 0;
                        const oy = parseInt(off.getAttribute('y'), 10) || 0;
                        x = Math.round((ox / this.slideCxEmu) * canvasW);
                        y = Math.round((oy / this.slideCyEmu) * canvasH);
                    }
                    if (ext) {
                        const cx = parseInt(ext.getAttribute('cx'), 10) || this.slideCxEmu;
                        const cy = parseInt(ext.getAttribute('cy'), 10) || this.slideCyEmu;
                        w = Math.round((cx / this.slideCxEmu) * canvasW);
                        h = Math.round((cy / this.slideCyEmu) * canvasH);
                    }
                }

                const imgFile = zip.files[imgMap[rId]];
                if (imgFile) {
                    const b64 = await imgFile.async('base64');
                    const fileExt = imgMap[rId].split('.').pop().toLowerCase();
                    const mimeType = fileExt === 'jpg' ? 'jpeg' : fileExt;
                    result.inline.push({
                        data: `data:image/${mimeType};base64,${b64}`,
                        x, y, w, h
                    });
                }
            }
        } catch (e) {
            this._log('warn', `Image extraction error: ${e.message}`);
        }

        return result;
    }

    async _drawTextShapes(ctx, xmlStr, canvasW, canvasH) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlStr, 'text/xml');

        // Get all shape elements (sp = shape)
        const shapes = doc.getElementsByTagName('p:sp');

        for (const shape of shapes) {
            // Get position
            const xfrm = shape.getElementsByTagNameNS(
                'http://schemas.openxmlformats.org/drawingml/2006/main', 'xfrm'
            )[0];

            let sx = 40, sy = 80, sw = canvasW - 80, sh = 400;

            if (xfrm) {
                const off = xfrm.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 'off'
                )[0];
                const ext = xfrm.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 'ext'
                )[0];

                if (off) {
                    const ox = parseInt(off.getAttribute('x') || 0, 10) || 0;
                    const oy = parseInt(off.getAttribute('y') || 0, 10) || 0;
                    sx = Math.round((ox / this.slideCxEmu) * canvasW);
                    sy = Math.round((oy / this.slideCyEmu) * canvasH);
                }
                if (ext) {
                    const cx = parseInt(ext.getAttribute('cx') || String(this.slideCxEmu), 10) || this.slideCxEmu;
                    const cy = parseInt(ext.getAttribute('cy') || String(this.slideCyEmu), 10) || this.slideCyEmu;
                    sw = Math.round((cx / this.slideCxEmu) * canvasW);
                    sh = Math.round((cy / this.slideCyEmu) * canvasH);
                }
            }

            // Get text paragraphs
            const paragraphs = shape.getElementsByTagNameNS(
                'http://schemas.openxmlformats.org/drawingml/2006/main', 'p'
            );

            let currentY = sy + 20;

            for (const para of paragraphs) {
                // Get font size from run properties
                const rPr = para.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 'rPr'
                )[0];

                const lstPr = shape.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 'lstStyle'
                )[0];

                // Detect if this is likely a title (large font or first shape)
                let fontSize = 16;
                let fontWeight = 'normal';
                let fontColor = '#1F2933';

                if (rPr) {
                    const sz = rPr.getAttribute('sz');
                    if (sz) fontSize = Math.max(10, Math.min(60, parseInt(sz) / 100));
                    const b = rPr.getAttribute('b');
                    if (b === '1') fontWeight = 'bold';

                    // Try to get color
                    const solidFill = rPr.getElementsByTagNameNS(
                        'http://schemas.openxmlformats.org/drawingml/2006/main', 'solidFill'
                    )[0];
                    if (solidFill) {
                        const srgb = solidFill.getElementsByTagNameNS(
                            'http://schemas.openxmlformats.org/drawingml/2006/main', 'srgbClr'
                        )[0];
                        if (srgb) fontColor = `#${srgb.getAttribute('val')}`;
                    }
                }

                // Get paragraph-level alignment
                const pPr = para.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 'pPr'
                )[0];
                const algn = pPr?.getAttribute('algn') || 'l';

                // Collect text runs
                const runs = para.getElementsByTagNameNS(
                    'http://schemas.openxmlformats.org/drawingml/2006/main', 't'
                );
                const lineText = Array.from(runs).map(r => r.textContent).join('').trim();

                if (!lineText) {
                    currentY += fontSize * 0.6;
                    continue;
                }

                // Scale font to fit within shape width
                const scaledFont = Math.min(fontSize, Math.max(10, sw / lineText.length * 1.6));
                const drawFont = Math.round(Math.min(fontSize, 48));

                ctx.font = `${fontWeight} ${drawFont}px system-ui, -apple-system, sans-serif`;
                ctx.fillStyle = fontColor;

                // Alignment
                let textX = sx + 10;
                ctx.textAlign = 'left';
                if (algn === 'ctr' || algn === 'center') {
                    ctx.textAlign = 'center';
                    textX = sx + sw / 2;
                } else if (algn === 'r') {
                    ctx.textAlign = 'right';
                    textX = sx + sw - 10;
                }

                // Word wrap
                const words = lineText.split(' ');
                let line = '';
                const lineHeight = drawFont * 1.3;

                for (const word of words) {
                    const test = line + (line ? ' ' : '') + word;
                    if (ctx.measureText(test).width > sw - 20 && line) {
                        if (currentY + lineHeight < sy + sh + 20) {
                            ctx.fillText(line, textX, currentY);
                            currentY += lineHeight;
                        }
                        line = word;
                    } else {
                        line = test;
                    }
                }
                if (line && currentY + lineHeight < sy + sh + 20) {
                    ctx.fillText(line, textX, currentY);
                    currentY += lineHeight;
                }

                currentY += drawFont * 0.3; // paragraph spacing
            }
        }
    }

    _drawImage(ctx, src, x, y, w, h) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, x, y, w, h);
                resolve();
            };
            img.onerror = reject;
            img.src = src;
        });
    }

    // -------------------------------------------------------------------------
    // Utility
    // -------------------------------------------------------------------------

    _progress(pct, message) {
        this._log(`[${pct}%] ${message}`);
        if (typeof this.options.onProgress === 'function') {
            this.options.onProgress(pct, message);
        }
    }

    _log(level, message) {
        if (typeof level === 'string' && !message) {
            // Called as _log('message') without level
            if (this.options.debug) console.log(`[PptxLoader] ${level}`);
            return;
        }
        if (!this.options.debug && level === 'debug') return;
        const fn = console[level] || console.log;
        fn(`[PptxLoader] ${message}`);
    }
}

// Export
window.PptxLoader = PptxLoader;