export function paginateCases(items, page = 1, pageSize = 20) {
  const size = [20, 50, 100].includes(pageSize) ? pageSize : 20;
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / size));
  const current = Math.min(Math.max(1, page), pageCount);
  return { items: items.slice((current - 1) * size, current * size),
    total, page: current, pageSize: size, pageCount };
}
