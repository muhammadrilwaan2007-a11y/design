
const sample = **AI Route Summary** - **Historical safety information** – The route\'s Safety Score and calibrated historical risk are currently unavailable so no numeric safety rating can be provided. - **Key modeled risk contributors (SHAP analysis)** * * **Road type** – contributed to higher modeled historical risk. * **Junction** contributed to higher modeled historical risk. * **Road-segment length** – contributed to lower modeled historical risk. The model places more weight on the road type and junction features, which push the historical risk upward, while the road length helps slightly.;

function parseBullets(text) {
  if (!text) return [];
  
  // 1. Remove markdown bold and italic asterisks
  let cleaned = text.replace(/[*_#]/g, ' ');
  
  // 2. Remove title prefixes like 'AI Route Summary' or 'Historical safety information'
  cleaned = cleaned.replace(/AI Route Summary\s*[-–:]*\s*/gi, '');
  cleaned = cleaned.replace(/Historical safety information\s*[-–:]*\s*/gi, '');
  cleaned = cleaned.replace(/Key modeled risk contributors(?:\s*\([^)]*\))?\s*[-–:]*\s*/gi, '');

  // 3. Split by newlines, bullet symbols (-, •), or inline bullet separators
  let rawItems = cleaned.split(/(?:\r?\n+|(?<=\s)[-–•]\s+|\s+[-–•]\s+)/g);

  const items = [];
  const headerWords = ['ai route summary', 'summary', 'historical safety information', 'key modeled risk contributors'];

  for (let item of rawItems) {
    let trimmed = item.trim().replace(/^[-–•:.\s]+/, '').replace(/[-–•:\s]+$/, '').trim();
    if (!trimmed) continue;

    const lower = trimmed.toLowerCase();
    if (headerWords.some(h => lower === h || lower.startsWith(h + ':'))) {
      continue;
    }

    if (trimmed.length > 150 && trimmed.includes('.')) {
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

  const uniqueItems = Array.from(new Set(items));
  return uniqueItems.slice(0, 5);
}

console.log(JSON.stringify(parseBullets(sample), null, 2));
