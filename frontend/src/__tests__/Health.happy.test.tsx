// frontend/src/__tests__/Health.happy.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HealthPage from '../pages/HealthPage';        // путь под себя
import { test, expect, vi, afterEach } from 'vitest';
import * as api from '../lib/api';               // ИМПОРТИРУЕМ ВЕСЬ МОДУЛЬ

afterEach(() => {
  vi.restoreAllMocks();
});

test('Health (happy path): рендерит OK и ключевые поля', async () => {
  const okData = {
    ok: true,
    api: { ok: true, version: 'dev' },
    db: { ok: true },
    redis: { ok: true },
    chain: { ok: true, chainId: 31337 },
    contracts: { ok: true, names: ['FileRegistry','AccessControlDFSP','DFSPAnchoring','MinimalForwarder'] },
    ipfs: { ok: true, id: '12D3Koo...' },
  };

  // КЛЮЧЕВОЕ: подменяем функцию в реальном модуле
  vi.spyOn(api, 'fetchHealth').mockResolvedValue(okData as any);

  render(
    <MemoryRouter>
      <HealthPage />
    </MemoryRouter>
  );

  expect(screen.getByRole('heading', { name: /health/i })).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByText(/overall:/i)).toBeInTheDocument();
    expect(screen.getByText(/version:\s*dev/i)).toBeInTheDocument();
    expect(screen.getByText(/chainid:\s*31337/i)).toBeInTheDocument();
    expect(screen.getByText(/fileregistry/i)).toBeInTheDocument();
    expect(screen.getByText(/^id:\s*/i)).toBeInTheDocument();
  });

  // и точно нет красной ошибки
  expect(screen.queryByText(/network error/i)).toBeNull();
});
