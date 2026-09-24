import * as content from './landing.content';

// The landing page of a trading product is where over-promising is most tempting.
// These tests turn the rules in landing.content.ts into checks (CLAUDE.md §4).

function collectStrings(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectStrings(item, out));
  else if (value !== null && typeof value === 'object') {
    Object.values(value).forEach((item) => collectStrings(item, out));
  }
  return out;
}

const allText = collectStrings(content);

// Phrases that promise or imply profit or safety.
const CLAIMS = [
  /\bgan(a|as|ar|e|es|ancia|ancias)\b/i,
  /rentab/i,
  /garantiz/i,
  /sin riesgo/i,
  /riesgo cero/i,
  /dinero f[aá]cil/i,
  /enriquec/i,
  /100\s?%\s*(seguro|rentable)/i,
];

// A claim is only acceptable when the sentence denies it.
const NEGATION = /\b(no|sin|nunca|ni)\b|desconf/i;

describe('landing copy', () => {
  it('has text to check', () => {
    expect(allText.length).toBeGreaterThan(40);
  });

  it('never promises profit or safety: any such word appears only in a denial', () => {
    const offenders = allText.filter(
      (text) => CLAIMS.some((claim) => claim.test(text)) && !NEGATION.test(text),
    );
    expect(offenders).toEqual([]);
  });

  it('actually denies it where it mentions it (guards the test itself)', () => {
    const mentions = allText.filter((text) => CLAIMS.some((claim) => claim.test(text)));
    expect(mentions.length).toBeGreaterThan(0);
    expect(content.HERO.note).toContain('Sin promesas de rentabilidad');
    expect(content.FOOTER.risk).toContain('no es asesoramiento financiero');
    expect(content.FOOTER.risk).toContain('riesgo de pérdida');
  });

  it('has no testimonials, reviews or invented customers', () => {
    expect(Object.keys(content).filter((key) => /testimon|review|cliente/i.test(key))).toEqual([]);
    expect(allText.filter((text) => /testimonio|“|”|opini[oó]n de clientes/i.test(text))).toEqual(
      [],
    );
  });

  it('labels everything as available or coming soon, never as both or neither', () => {
    const tagged = [
      ...content.BENEFITS.items,
      ...content.HOW_IT_WORKS.steps,
      ...content.USE_CASES.items,
    ];
    expect(tagged.length).toBeGreaterThan(10);
    for (const item of tagged) {
      expect(['now', 'soon'], item.title).toContain(item.availability);
    }
    // The unbuilt things are honest about it.
    const soon = tagged.filter((item) => item.availability === 'soon').map((i) => i.title);
    expect(soon).toEqual(
      expect.arrayContaining([
        'Señales explicadas y simulación DEMO',
        'Simular una estrategia en DEMO',
        'Probar una idea sobre datos pasados',
      ]),
    );
  });

  it('states facts about the product, not performance figures', () => {
    expect(content.FACTS).toHaveLength(4);
    for (const fact of content.FACTS) {
      expect(fact.value).toMatch(/^(\d+|\d+ %)$/);
      expect(fact.label).not.toMatch(/retorno|ganancia|rentab|rendimiento/i);
    }
  });

  it('keeps the navigation anchors and the section ids in step', () => {
    const anchors = content.NAV_LINKS.map((link) => link.href);
    const ids = [content.HOW_IT_WORKS.id, content.BENEFITS.id, content.FAQ.id].map(
      (id) => `#${id}`,
    );
    expect(anchors.sort()).toEqual(ids.sort());
  });

  it('answers every question and covers the risks a visitor would ask about', () => {
    expect(content.FAQ.items.length).toBeGreaterThanOrEqual(6);
    for (const item of content.FAQ.items) {
      expect(item.question.length).toBeGreaterThan(8);
      expect(item.answer.length).toBeGreaterThan(30);
    }
    const questions = content.FAQ.items.map((item) => item.question).join(' ');
    expect(questions).toMatch(/opera por m[ií]/i);
    expect(questions).toMatch(/resultados/i);
    expect(questions).toMatch(/datos/i);
  });

  it('is written in Spanish with its accents', () => {
    expect(content.HERO.title).toBe('Entiende el mercado antes de operar.');
    expect(allText.join(' ')).toMatch(/[áéíóúñ]/);
  });
});
