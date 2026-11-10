// Color de marca de Runch. Para cambiarlo, toca SOLO las variables --brand* de index.html (bloque <style>):
// toda la app (botones, barra, chat, logotipo, onboarding) las usa desde aquí.
//   --brand        color principal (botones, iconos, logotipo en modo claro)
//   --brand-dark   el mismo, más oscuro (botón pulsado)
//   --brand-light  el mismo, más claro (texto e iconos sobre fondo oscuro)
//   --brand-ink    el que toca según el tema (principal en claro, claro en oscuro)
//   --brand-cream  crema de la marca (logotipo en modo oscuro)
//   --lavanda / --pistacho / --mar (+ *-ink): acentos de cada sección (ver SECTION_INK)
export const BRAND = 'var(--brand)';
export const BRAND_DARK = 'var(--brand-dark)';
export const BRAND_INK = 'var(--brand-ink)';

/** Color de cada sección (barra de abajo, pestañas): olivo, lavanda, pistacho y mar. */
export const SECTION_INK: Record<string, string> = {
  hoy: 'var(--brand-ink)', salud: 'var(--lavanda-ink)', entreno: 'var(--pistacho-ink)', analisis: 'var(--mar-ink)',
};
export const sectionInk = (key: string) => SECTION_INK[key] ?? BRAND_INK;

/** El color de marca mezclado con transparente (fondos suaves): `brandTint(14)` = 14 %. */
export const brandTint = (pct: number, c = BRAND) => `color-mix(in srgb, ${c} ${pct}%, transparent)`;
