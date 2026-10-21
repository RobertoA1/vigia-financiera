import test from 'node:test';
import assert from 'node:assert/strict';
import {publicNavigationOrigin, validateApiBase} from '../shared.js';
test('only origin leaves browser, no secrets or private content', () => {
  assert.equal(publicNavigationOrigin('https://www.viabcp.com/client/secret?otp=123#token'), 'https://www.viabcp.com/');
  for (const url of ['file:///etc/passwd','chrome://settings','http://localhost','http://192.168.0.1','http://[::1]','https://u:p@bank.invalid']) assert.throws(() => publicNavigationOrigin(url));
});
test('API requires HTTPS except local development and rejects URL credentials', () => {
  assert.equal(validateApiBase('http://localhost:8000/api/v1/'), 'http://localhost:8000/api/v1');
  assert.equal(validateApiBase('https://api.example.com/api/v1'), 'https://api.example.com/api/v1');
  for (const url of ['http://api.example.com','https://user:key@api.example.com','https://api.example.com?token=1']) assert.throws(() => validateApiBase(url));
});
