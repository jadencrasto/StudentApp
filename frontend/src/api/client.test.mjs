import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import client, { setOnUnauthorizedHandler, isPublicRoute } from './client.js';

describe('client.js 401 interceptor & route logic', () => {
  let unauthorizedCallCount = 0;

  beforeEach(() => {
    unauthorizedCallCount = 0;
    setOnUnauthorizedHandler(() => {
      unauthorizedCallCount++;
    });

    // Mock minimal browser globals for Node test environment
    globalThis.localStorage = {
      store: {},
      removeItem(key) { delete this.store[key]; },
      setItem(key, val) { this.store[key] = val; },
      getItem(key) { return this.store[key]; },
    };
  });

  test('isPublicRoute identifies public and protected paths correctly', () => {
    assert.equal(isPublicRoute('/'), true);
    assert.equal(isPublicRoute('/login'), true);
    assert.equal(isPublicRoute('/login/'), true);
    assert.equal(isPublicRoute('/register'), true);
    assert.equal(isPublicRoute('/login?from=/dashboard'), true);

    assert.equal(isPublicRoute('/dashboard'), false);
    assert.equal(isPublicRoute('/admin'), false);
    assert.equal(isPublicRoute('/super-admin'), false);
    assert.equal(isPublicRoute('/change-password'), false);
    assert.equal(isPublicRoute('/onboarding'), false);
  });

  test('401 from /auth/me does NOT trigger redirect handler', async () => {
    globalThis.window = {
      location: { pathname: '/dashboard' },
      dispatchEvent: () => {},
    };

    // Find the response error interceptor
    const errorInterceptor = client.interceptors.response.handlers[0].rejected;

    const error = {
      response: { status: 401 },
      config: { url: '/auth/me' },
    };

    await assert.rejects(async () => {
      await errorInterceptor(error);
    });

    assert.equal(unauthorizedCallCount, 0, 'Should not redirect for /auth/me 401');
  });

  test('401 from /classroom/ does NOT trigger redirect handler', async () => {
    globalThis.window = {
      location: { pathname: '/dashboard' },
      dispatchEvent: () => {},
    };

    const errorInterceptor = client.interceptors.response.handlers[0].rejected;

    const error = {
      response: { status: 401 },
      config: { url: '/classroom/courses' },
    };

    await assert.rejects(async () => {
      await errorInterceptor(error);
    });

    assert.equal(unauthorizedCallCount, 0, 'Should not redirect for third-party classroom 401');
  });

  test('401 on a public route (e.g. /login) does NOT trigger redirect handler', async () => {
    globalThis.window = {
      location: { pathname: '/login' },
      dispatchEvent: () => {},
    };

    const errorInterceptor = client.interceptors.response.handlers[0].rejected;

    const error = {
      response: { status: 401 },
      config: { url: '/auth/login' },
    };

    await assert.rejects(async () => {
      await errorInterceptor(error);
    });

    assert.equal(unauthorizedCallCount, 0, 'Should not redirect when already on /login');
  });

  test('401 on a protected route triggers unauthorized router handler (no full reload)', async () => {
    globalThis.window = {
      location: { pathname: '/dashboard/assignments' },
      dispatchEvent: () => {},
    };

    const errorInterceptor = client.interceptors.response.handlers[0].rejected;

    const error = {
      response: { status: 401 },
      config: { url: '/assignments' },
    };

    await assert.rejects(async () => {
      await errorInterceptor(error);
    });

    assert.equal(unauthorizedCallCount, 1, 'Should call router handler to navigate to login');
  });
});

