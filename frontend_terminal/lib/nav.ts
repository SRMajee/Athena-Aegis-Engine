export interface NavItem {
  href: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: '/strategy-manager', label: 'Strategy Manager' },
  { href: '/backtest', label: 'Backtest' },
  { href: '/orders-trades', label: 'Orders & Trades' },
  { href: '/database', label: 'Database' },
];
