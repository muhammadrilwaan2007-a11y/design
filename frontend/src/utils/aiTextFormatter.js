/**
 * frontend/src/utils/aiTextFormatter.js
 * =====================================
 * Utilities for cleaning and formatting AI responses into crisp bullet points.
 * Removes markdown asterisks, raw bold tags, extraneous headers, and splits
 * long narrative paragraphs into concise bullet items.
 */

export function parseAiBullets(text, fallbackText = '') {
  const source = (text && text.trim()) || fallbackText;
  if (!source) return [];

  // 1. Remove markdown bold and italic asterisks
  let normalized = source
    .replace(/\*\*/g, '')
    .replace(/(?:\r?\n|\s+)(?:[*•-]\s*)+/g, '\n- ')
    .replace(/AI Route Summary\s*[-–:]*\s*/gi, '')
    .replace(/Historical safety information\s*[-–:]*\s*/gi, '')
    .replace(/Key modeled risk contributors(?:\s*\([^)]*\))?\s*[-–:]*\s*/gi, '');

  const rawLines = normalized.split(/\r?\n+/);
  const items = [];
  const headerWords = [
    'ai route summary',
    'summary',
    'historical safety information',
    'key modeled risk contributors',
    'shap analysis',
  ];

  for (let line of rawLines) {
    let trimmed = line.trim().replace(/^[-–•:.\s]+/, '').replace(/[-–•:\s]+$/, '').trim();
    if (!trimmed) continue;

    const lower = trimmed.toLowerCase();
    if (headerWords.some((h) => lower === h || lower.startsWith(h + ':'))) {
      continue;
    }

    // Split long blocks with multiple sentences into separate bullets
    if (trimmed.length > 140 && trimmed.includes('.')) {
      const sentences = trimmed.split(/(?<=[.!?])\s+/);
      for (let s of sentences) {
        let sc = s.trim().replace(/^[-–•:.\s]+/, '').trim();
        if (sc.length > 10) {
          sc = sc.charAt(0).toUpperCase() + sc.slice(1);
          items.push(sc);
        }
      }
    } else {
      if (trimmed.length > 10) {
        trimmed = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
        items.push(trimmed);
      }
    }
  }

  // Deduplicate and cap to 5 bullet points
  const uniqueItems = Array.from(new Set(items));
  return uniqueItems.slice(0, 5);
}
