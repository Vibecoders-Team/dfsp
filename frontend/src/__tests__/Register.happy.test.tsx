import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import RegisterPage from '../pages/Register';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

// Мокаем модуль ethers (нужна только verifyTypedData)
vi.mock('ethers', () => ({
  ethers: {
    verifyTypedData: vi.fn(),
  },
}));

// Импортируем то, что будем подменять (ВАЖНО: те же спецификаторы, что и в компоненте)
import * as keychain from '../lib/keychain';
import * as api from '../lib/api';
import { ethers } from 'ethers';

const addr = '0x59f32A79A841F403731a157A7c48d29cb9ED51E8';
const rsaPub = '-----BEGIN RSA PUBLIC KEY-----\nMIIBCg...==\n-----END RSA PUBLIC KEY-----';

beforeEach(() => {
  // По умолчанию: кошелька нет (кнопка Register disabled)
  vi.spyOn(keychain, 'getEOA').mockResolvedValue(undefined as any);
  // Эти функции будем переопределять в самих тестах при необходимости
  vi.spyOn(keychain, 'ensureEOA').mockResolvedValue({ address: addr } as any);
  vi.spyOn(keychain, 'ensureRSA').mockResolvedValue({ publicPem: rsaPub } as any);
  vi.spyOn(keychain, 'signLoginTyped').mockResolvedValue('0xsig' as any);
  (ethers.verifyTypedData as unknown as vi.Mock).mockReturnValue(addr);

  // API моки
  vi.spyOn(api, 'postChallenge').mockResolvedValue({
    challenge_id: 'chal-1',
    nonce: '0x1234',
  } as any);

  vi.spyOn(api, 'postRegister').mockResolvedValue({
    access: 'acc-token',
    refresh: 'ref-token',
  } as any);
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('RegisterPage (happy path)', () => {
  test('Generate Keys: показывает адрес, public PEM и включает Register', async () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    );

    // изначально адрес пуст (—), кнопка Register выключена
    expect(screen.getByRole('button', { name: /register/i })).toBeDisabled();

    // генерим ключи
    await userEvent.click(screen.getByRole('button', { name: /generate keys/i }));

    // статус «Keys ready.» и публичный ключ на экране
    await waitFor(() =>
      expect(screen.getByText(/keys ready\./i)).toBeInTheDocument()
    );
    expect(screen.getByText(new RegExp(addr.slice(0, 10), 'i'))).toBeInTheDocument();
    expect(
        screen.getByRole('heading', { name: /rsa public \(pem\)/i })
    ).toBeInTheDocument();

// и дополнительно содержимое ключа:
expect(screen.getByText(/BEGIN RSA PUBLIC KEY/)).toBeInTheDocument();
    expect(screen.getByText(/BEGIN RSA PUBLIC KEY/)).toBeInTheDocument();

    // теперь кнопка Register должна быть активной
    expect(screen.getByRole('button', { name: /register/i })).not.toBeDisabled();
  });

// frontend/src/__tests__/pages/Register.happy.test.tsx (фрагмент: второй тест)
test('Register: happy path → токены в localStorage', async () => {
  render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>
  );

  // подготовка: генерим ключи (делает кнопку активной)
  await userEvent.click(screen.getByRole('button', { name: /generate keys/i }));
  await screen.findByText(/keys ready\./i);

  // действие: регистрируемся
  await userEvent.click(screen.getByRole('button', { name: /^register$/i }));

  // итог: видим завершение
  await screen.findByText(/^done\./i);

  // побочные эффекты: токены записаны
  expect(localStorage.getItem('ACCESS_TOKEN')).toBe('acc-token');
  expect(localStorage.getItem('REFRESH_TOKEN')).toBe('ref-token');

  // и вызовы шагов были сделаны (аргументы можно уточнить при желании)
  expect(api.postChallenge).toHaveBeenCalledTimes(1);
  expect(keychain.signLoginTyped).toHaveBeenCalledTimes(1);
  expect(api.postRegister).toHaveBeenCalledTimes(1);
});
});
