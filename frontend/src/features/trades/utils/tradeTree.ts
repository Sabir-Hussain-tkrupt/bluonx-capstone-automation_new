/**
 * Helpers for trades with subtrades (one level: trade → subtrade).
 *
 * Rule shared with the database (migration 20261117): a trade that HAS
 * subtrades cannot be assigned directly to a task, vendor or template; one of
 * its subtrades must be chosen. Trades without subtrades are assigned as before.
 *
 * Every helper works on the list the pickers already load (active trades), so
 * "has subtrades" means "has active subtrades".
 */

export interface TradeLike {
  id: string;
  name: string;
  parent_trade_id?: string | null;
}

export interface TradeNode<T extends TradeLike> {
  trade: T;
  children: T[];
}

export const SUBTRADE_SEPARATOR = ' › ';

const byName = <T extends TradeLike>(a: T, b: T) => a.name.localeCompare(b.name);

/** Top-level trades (sorted by name) with their subtrades (sorted by name).
 *  A subtrade whose parent is not in the list is shown as top-level. */
export function buildTradeTree<T extends TradeLike>(trades: T[]): TradeNode<T>[] {
  const ids = new Set(trades.map((t) => t.id));
  const children = new Map<string, T[]>();
  const roots: T[] = [];
  for (const t of trades) {
    if (t.parent_trade_id && ids.has(t.parent_trade_id)) {
      const list = children.get(t.parent_trade_id) ?? [];
      list.push(t);
      children.set(t.parent_trade_id, list);
    } else {
      roots.push(t);
    }
  }
  return roots.sort(byName).map((trade) => ({
    trade,
    children: (children.get(trade.id) ?? []).sort(byName),
  }));
}

/** True when the trade has subtrades in `trades` (so it must not be assigned directly). */
export function hasSubtrades(trades: TradeLike[], tradeId: string): boolean {
  return trades.some((t) => t.parent_trade_id === tradeId);
}

/** "Electrical › Commercial" for a subtrade, plain name otherwise. */
export function tradeLabel(trades: TradeLike[], tradeId: string | null | undefined): string {
  if (!tradeId) return '';
  const t = trades.find((x) => x.id === tradeId);
  if (!t) return '';
  const parent = t.parent_trade_id ? trades.find((x) => x.id === t.parent_trade_id) : undefined;
  return parent ? `${parent.name}${SUBTRADE_SEPARATOR}${t.name}` : t.name;
}

/** A trade's subtrades in `trades`, sorted by name. */
export function subtradesOf<T extends TradeLike>(trades: T[], tradeId: string): T[] {
  return trades.filter((t) => t.parent_trade_id === tradeId).sort(byName);
}

/**
 * Options for picking a trade to ASSIGN: trades without subtrades, plus every
 * subtrade as "Trade › Subtrade". Trades that have subtrades are left out
 * (their subtrades stand in for them). `keepId` keeps a current value listed
 * even if it would otherwise be filtered (e.g. an older task on a trade that
 * later got subtrades).
 */
export function assignableTradeOptions(
  trades: TradeLike[],
  keepId?: string | null,
): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  for (const node of buildTradeTree(trades)) {
    if (node.children.length === 0 || node.trade.id === keepId) {
      out.push({ value: node.trade.id, label: node.trade.name });
    }
    for (const c of node.children) {
      out.push({ value: c.id, label: `${node.trade.name}${SUBTRADE_SEPARATOR}${c.name}` });
    }
  }
  return out;
}

/**
 * Options for FILTERING: every trade, with subtrades listed under their trade.
 * Filtering by a trade also matches its subtrades (the server expands it).
 */
export function tradeFilterOptions(trades: TradeLike[]): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  for (const node of buildTradeTree(trades)) {
    out.push({
      value: node.trade.id,
      label: node.children.length ? `${node.trade.name} (all)` : node.trade.name,
    });
    for (const c of node.children) {
      out.push({ value: c.id, label: `${node.trade.name}${SUBTRADE_SEPARATOR}${c.name}` });
    }
  }
  return out;
}
