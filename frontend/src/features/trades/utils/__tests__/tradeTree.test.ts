import { describe, expect, it } from 'vitest';
import {
  assignableTradeOptions,
  buildTradeTree,
  hasSubtrades,
  tradeFilterOptions,
  tradeLabel,
} from '../tradeTree';

const electrical = { id: 'e', name: 'Electrical', parent_trade_id: null };
const commercial = { id: 'ec', name: 'Commercial', parent_trade_id: 'e' };
const residential = { id: 'er', name: 'Residential', parent_trade_id: 'e' };
const grading = { id: 'g', name: 'Grading', parent_trade_id: null };
const trades = [residential, grading, commercial, electrical];

describe('tradeTree', () => {
  it('groups subtrades under their trade, both sorted by name', () => {
    const tree = buildTradeTree(trades);
    expect(tree.map((n) => n.trade.name)).toEqual(['Electrical', 'Grading']);
    expect(tree[0].children.map((c) => c.name)).toEqual(['Commercial', 'Residential']);
  });

  it('labels subtrades with their trade', () => {
    expect(tradeLabel(trades, 'ec')).toBe('Electrical › Commercial');
    expect(tradeLabel(trades, 'g')).toBe('Grading');
    expect(tradeLabel(trades, 'missing')).toBe('');
  });

  it('forces a subtrade when assigning a trade that has subtrades', () => {
    expect(hasSubtrades(trades, 'e')).toBe(true);
    expect(assignableTradeOptions(trades)).toEqual([
      { value: 'ec', label: 'Electrical › Commercial' },
      { value: 'er', label: 'Electrical › Residential' },
      { value: 'g', label: 'Grading' },
    ]);
  });

  it('keeps a legacy value that points at a trade with subtrades', () => {
    expect(assignableTradeOptions(trades, 'e').map((o) => o.value)).toEqual(['e', 'ec', 'er', 'g']);
  });

  it('filter options include every trade, parents marked "(all)"', () => {
    expect(tradeFilterOptions(trades).map((o) => o.label)).toEqual([
      'Electrical (all)',
      'Electrical › Commercial',
      'Electrical › Residential',
      'Grading',
    ]);
  });
});
