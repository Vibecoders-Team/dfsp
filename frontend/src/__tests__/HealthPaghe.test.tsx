import '@testing-library/jest-dom';
import { render, screen, within } from '@testing-library/react';
import HealthPage from '../pages/HealthPage';
import { vi, test, expect, afterEach } from 'vitest';
import App from '../app/App'


vi.stubGlobal('fetch', vi.fn(async () => ({
  ok: true,
  json: async () => ({ status: 'ok', uptime: 1 }),
})));

afterEach(() => {
  vi.resetAllMocks();
});

test('pings health and shows ok', async () => {
  render(<HealthPage />);

  const statusEl = await screen.findByText(/Status:/i);
  expect(statusEl).toBeInTheDocument();

  const okEl = within(statusEl).getByText(/\bok\b/i);
  expect(okEl).toBeInTheDocument();
});

test('renders app heading', () => {
  render(<App />)
  expect(screen.getByRole('heading')).toBeInTheDocument()
})
