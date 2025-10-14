// src/__tests__/HealthPage.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { test, expect, vi } from 'vitest';

// 1) мок перед импортом компонента
vi.mock('../lib/api', () => {
  return {
    fetchHealth: vi.fn(),   // создаём мок
  };
});

import { fetchHealth } from '../lib/api';  // та же строка, что в компоненте
import HealthPage from '../pages/HealthPage';

test('pings health and shows ok', async () => {
  (fetchHealth as unknown as jest.Mock).mockResolvedValue({
    ok: true,
    api: { ok: true, version: 'dev' },
    db: { ok: true },
    redis: { ok: true },
    chain: { ok: true, chainId: 31337 },
    contracts: { ok: true, names: ['FileRegistry'] },
    ipfs: { ok: true, id: '12D3Koo...' },
  });

  render(<MemoryRouter><HealthPage /></MemoryRouter>);

  await waitFor(() => {
    expect(screen.getByText(/overall:/i)).toBeInTheDocument();
  });
});
