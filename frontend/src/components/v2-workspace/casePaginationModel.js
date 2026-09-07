export const DEFAULT_CASE_PAGE_SIZE = 15;
export const CASE_PAGE_SIZE_OPTIONS = [15, 30, 50, 100];

export function paginateCases(items, page = 1, pageSize = DEFAULT_CASE_PAGE_SIZE) {
  const size = CASE_PAGE_SIZE_OPTIONS.includes(pageSize) ? pageSize : DEFAULT_CASE_PAGE_SIZE;
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / size));
  const current = Math.min(Math.max(1, page), pageCount);
  return { items: items.slice((current - 1) * size, current * size),
    total, page: current, pageSize: size, pageCount };
}
