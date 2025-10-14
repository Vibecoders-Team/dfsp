import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Home from '../pages/Home';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>
  );
}

describe('Home page (happy path)', () => {
  beforeEach(() => cleanup());

  it('рендерит заголовок, навигацию и дефолтные значения', () => {
    renderHome();

    // заголовок
    expect(screen.getByRole('heading', { name: /dfsp/i })).toBeInTheDocument();

    // навигация (ссылки)
    expect(screen.getByRole('link', { name: /health/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /register/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /login/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /upload/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /files/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /verify/i })).toBeInTheDocument();

    // сервисная секция: проверяем дефолты (т.к. nullish-оператор в компоненте)
    expect(screen.getByText(/API:\s*http:\/\/localhost:8000/i)).toBeInTheDocument();
    expect(screen.getByText(/IPFS gateway:\s*http:\/\/localhost:8080/i)).toBeInTheDocument();
    expect(screen.getByText(/Chain ID:\s*31337/i)).toBeInTheDocument();
  });

  it('использует значения из import.meta.env при их наличии', () => {
    // сохраним текущее окружение
    const prevEnv = { ...import.meta.env };

    // подставим тестовые значения
    Object.assign(import.meta.env, {
      VITE_API_BASE: 'https://api.example.com',
      VITE_IPFS_PUBLIC_GATEWAY: 'https://ipfs.example.com',
      VITE_CHAIN_ID: '42',
    });

    renderHome();

    expect(screen.getByText(/API:\s*https:\/\/api\.example\.com/i)).toBeInTheDocument();
    expect(
      screen.getByText(/IPFS gateway:\s*https:\/\/ipfs\.example\.com/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Chain ID:\s*42/i)).toBeInTheDocument();

    // откатить окружение, чтобы не влиять на другие тесты
    Object.keys(import.meta.env).forEach((k) => delete (import.meta.env as any)[k]);
    Object.assign(import.meta.env, prevEnv);
  });
});
