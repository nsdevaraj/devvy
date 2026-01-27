import { jsPDF } from 'jspdf';
import * as pdfjsLib from 'pdfjs-dist';

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

const getConcurrencyLimit = () => {
  if (typeof navigator !== 'undefined' && navigator.hardwareConcurrency) {
    // Use hardware threads count directly to avoid context switching overhead
    return Math.max(1, navigator.hardwareConcurrency);
  }
  return 4; // Conservative default
};

export const compressPDF = async (
  file,
  onProgress
) => {
  return new Promise(async (resolve, reject) => {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const data = new Uint8Array(arrayBuffer);

        const loadingTask = pdfjsLib.getDocument({ data });
        const pdf = await loadingTask.promise;
        const totalPages = pdf.numPages;

        let pdfDoc = null;

        // Parallel processing setup
        const concurrency = getConcurrencyLimit();
        let currentIndex = 1;
        let completedCount = 0;

        // Interleaved assembly state to reduce memory usage and pipeline operations
        let nextPageToAdd = 1;
        const bufferedPages = new Map();

        const worker = async () => {
             let canvas;
             let context;
             const useOffscreen = typeof OffscreenCanvas !== 'undefined';

             // Reuse canvas to reduce DOM allocation overhead (Performance Optimization)
             if (useOffscreen) {
                 canvas = new OffscreenCanvas(1, 1);
                 context = canvas.getContext('2d');
             } else {
                 canvas = document.createElement('canvas');
                 context = canvas.getContext('2d');
             }

             if (!context) throw new Error('Canvas context not available');

             while (currentIndex <= totalPages) {
                 const i = currentIndex++;

                 const page = await pdf.getPage(i);
                 // Render at 1.5 scale for reasonable quality before compression
                 const renderScale = 1.5;
                 const viewport = page.getViewport({ scale: renderScale });

                 if (canvas.width !== viewport.width || canvas.height !== viewport.height) {
                     canvas.width = viewport.width;
                     canvas.height = viewport.height;
                 } else {
                     context.clearRect(0, 0, canvas.width, canvas.height);
                 }

                 await page.render({ canvasContext: context, viewport }).promise;

                 let imgData;

                 if (useOffscreen && (canvas instanceof OffscreenCanvas)) {
                     const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.5 });
                     const buffer = await blob.arrayBuffer();
                     imgData = new Uint8Array(buffer);
                 } else {
                     // Compress to JPEG with 0.5 quality
                     // Optimization: Use toBlob (async) to yield the event loop and avoid blocking the main thread during compression
                     const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.5));
                     if (!blob) throw new Error('Blob creation failed');

                     const buffer = await blob.arrayBuffer();
                     imgData = new Uint8Array(buffer);
                 }

                 // Calculate original page dimensions in points
                 const pdfPageWidth = viewport.width / renderScale;
                 const pdfPageHeight = viewport.height / renderScale;
                 const orientation = pdfPageWidth > pdfPageHeight ? 'l' : 'p';

                 // Interleaved Assembly: Add to buffer and flush sequential pages
                 bufferedPages.set(i, { imgData, pdfPageWidth, pdfPageHeight, orientation });

                 while (bufferedPages.has(nextPageToAdd)) {
                     const nextData = bufferedPages.get(nextPageToAdd);
                     const { imgData, pdfPageWidth, pdfPageHeight, orientation } = nextData;

                     if (!pdfDoc) {
                        pdfDoc = new jsPDF({
                            orientation: orientation,
                            unit: 'pt',
                            format: [pdfPageWidth, pdfPageHeight]
                        });
                    } else {
                        pdfDoc.addPage([pdfPageWidth, pdfPageHeight], orientation);
                    }
                    pdfDoc.addImage(imgData, 'JPEG', 0, 0, pdfPageWidth, pdfPageHeight, undefined, 'FAST');

                    bufferedPages.delete(nextPageToAdd);
                    nextPageToAdd++;
                 }

                 completedCount++;
                 onProgress && onProgress((completedCount / totalPages) * 100);
             }
        };

        // Run workers
        await Promise.all(Array.from({ length: Math.min(concurrency, totalPages) }, worker));

        if (pdfDoc) {
            const blob = pdfDoc.output('blob');
            resolve(blob);
        } else {
            reject(new Error('No pages processed'));
        }

    } catch (error) {
        console.error("Compression error:", error);
        reject(error);
    }
  });
};

export const flattenPDF = async (
  file,
  onProgress,
  password
) => {
  return new Promise(async (resolve, reject) => {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const data = new Uint8Array(arrayBuffer);

        const loadingTask = pdfjsLib.getDocument({ data, password });
        const pdf = await loadingTask.promise;
        const totalPages = pdf.numPages;

        let pdfDoc = null;

        // Parallel processing setup
        const concurrency = getConcurrencyLimit();
        let currentIndex = 1;
        let completedCount = 0;

        // Interleaved assembly state to reduce memory usage and pipeline operations
        let nextPageToAdd = 1;
        const bufferedPages = new Map();

        const worker = async () => {
             let canvas;
             let context;
             const useOffscreen = typeof OffscreenCanvas !== 'undefined';

             // Reuse canvas to reduce DOM allocation overhead
             if (useOffscreen) {
                 canvas = new OffscreenCanvas(1, 1);
                 context = canvas.getContext('2d');
             } else {
                 canvas = document.createElement('canvas');
                 context = canvas.getContext('2d');
             }

             if (!context) throw new Error('Canvas context not available');

             while (currentIndex <= totalPages) {
                 const i = currentIndex++;

                 const page = await pdf.getPage(i);
                 // Render at higher scale for better quality (flattening shouldn't degrade quality too much)
                 const renderScale = 2.0;
                 const viewport = page.getViewport({ scale: renderScale });

                 if (canvas.width !== viewport.width || canvas.height !== viewport.height) {
                     canvas.width = viewport.width;
                     canvas.height = viewport.height;
                 } else {
                     context.clearRect(0, 0, canvas.width, canvas.height);
                 }

                 await page.render({ canvasContext: context, viewport }).promise;

                 let imgData;
                 let blob;

                 if (useOffscreen && (canvas instanceof OffscreenCanvas)) {
                     blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.95 });
                 } else {
                     // Use PNG or high quality JPEG for flattening
                     blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
                 }

                 if (!blob) throw new Error('Blob creation failed');

                 const buffer = await blob.arrayBuffer();
                 imgData = new Uint8Array(buffer);

                 // Calculate original page dimensions in points
                 const pdfPageWidth = viewport.width / renderScale;
                 const pdfPageHeight = viewport.height / renderScale;
                 const orientation = pdfPageWidth > pdfPageHeight ? 'l' : 'p';

                 // Interleaved Assembly: Add to buffer and flush sequential pages
                 bufferedPages.set(i, { imgData, pdfPageWidth, pdfPageHeight, orientation });

                 while (bufferedPages.has(nextPageToAdd)) {
                     const nextData = bufferedPages.get(nextPageToAdd);
                     const { imgData, pdfPageWidth, pdfPageHeight, orientation } = nextData;

                     if (!pdfDoc) {
                        pdfDoc = new jsPDF({
                            orientation: orientation,
                            unit: 'pt',
                            format: [pdfPageWidth, pdfPageHeight]
                        });
                    } else {
                        pdfDoc.addPage([pdfPageWidth, pdfPageHeight], orientation);
                    }
                    pdfDoc.addImage(imgData, 'JPEG', 0, 0, pdfPageWidth, pdfPageHeight, undefined, 'FAST');

                    bufferedPages.delete(nextPageToAdd);
                    nextPageToAdd++;
                 }

                 completedCount++;
                 onProgress && onProgress((completedCount / totalPages) * 100);
             }
        };

        // Run workers
        await Promise.all(Array.from({ length: Math.min(concurrency, totalPages) }, worker));

        if (pdfDoc) {
            const blob = pdfDoc.output('blob');
            resolve(blob);
        } else {
            reject(new Error('No pages processed'));
        }

    } catch (error) {
        console.error("Flattening error:", error);
        reject(error);
    }
  });
};
