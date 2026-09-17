import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: BASE,
  timeout: 10000,
});

/**
 * Wrapper: always returns { data, error } — never throws.
 */
async function request(method, url, body = null) {
  try {
    const config = { method, url };
    if (body) config.data = body;
    const response = await client(config);
    return { data: response.data, error: null };
  } catch (err) {
    const message =
      err.response?.data?.detail ||
      err.message ||
      'Unknown error';
    return { data: null, error: message };
  }
}

export async function getHealth() {
  return request('get', '/health');
}

export async function getContainers() {
  return request('get', '/containers');
}

export async function getIncidents(page = 1, limit = 20) {
  return request('get', `/incidents?page=${page}&limit=${limit}`);
}

export async function getActions(page = 1, limit = 20) {
  return request('get', `/actions?page=${page}&limit=${limit}`);
}

export async function getApprovals() {
  return request('get', '/approvals');
}

export async function getMetrics() {
  return request('get', '/metrics');
}

export async function postApprove(approvalId, approved, operator = 'dashboard_user') {
  return request('post', `/approve/${approvalId}`, { approved, operator });
}
