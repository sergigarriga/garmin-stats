import { dateLong, dateShort, monthShort } from './format';
import { toDate } from './data';

type Ctx = { location: string };

/** Eje de tiempo continuo (líneas). */
export function timeAxis(dates: Date[]) {
  const spanDays = dates.length > 1 ? (dates[dates.length - 1].getTime() - dates[0].getTime()) / 864e5 : 0;
  return {
    data: dates,
    scaleType: 'time' as const,
    disableLine: true,
    disableTicks: true,
    tickNumber: narrow() ? 4 : 8,
    valueFormatter: (v: Date, ctx: Ctx) =>
      ctx.location === 'tick' ? (spanDays > 120 ? monthShort(v) : dateShort(v)) : dateLong(v),
  };
}

/** Eje de categorías por fecha (barras), mostrando solo algunas etiquetas. */
const narrow = () => typeof window !== 'undefined' && window.innerWidth < 600;

export function bandAxis(isoDates: string[], opts: { weekly?: boolean } = {}) {
  const n = isoDates.length;
  const step = Math.max(1, Math.ceil(n / (narrow() ? 4 : 8)));
  const spanDays = n > 1 ? (toDate(isoDates[n - 1]).getTime() - toDate(isoDates[0]).getTime()) / 864e5 : 0;
  return {
    data: isoDates,
    scaleType: 'band' as const,
    disableLine: true,
    disableTicks: true,
    categoryGapRatio: n > 60 ? 0.15 : 0.3,
    tickLabelInterval: (_: unknown, i: number) => i % step === 0,
    valueFormatter: (v: string, ctx: Ctx) => {
      const d = toDate(v);
      if (ctx.location === 'tick') return spanDays > 200 ? monthShort(d) : dateShort(d);
      return opts.weekly ? `Semana del ${dateShort(d)}` : dateLong(d);
    },
  };
}

export const yClean = { disableLine: true, disableTicks: true } as const;
