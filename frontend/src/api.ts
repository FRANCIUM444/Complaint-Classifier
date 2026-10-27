const API_BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000').replace(/\/$/, '')
export function getToken() { return sessionStorage.getItem('campuscare_token') }
export function setToken(token: string | null) { token ? sessionStorage.setItem('campuscare_token', token) : sessionStorage.removeItem('campuscare_token') }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`)
  return payload as T
}

export type User = { id: number; name: string; email: string; role: 'student' | 'staff' | 'admin' | 'moderator' }
export type Complaint = {
  id: number; complaint_id: string; description: string; location: string; category: string;
  predicted_category: string; priority: string; predicted_priority: string; sentiment: string;
  suggested_department: string; assigned_department: string | null; status: string;
  created_at: string; resolution_details?: string | null
}
export type Analysis = {
  category: string; category_confidence: number; priority: string; priority_confidence: number;
  location: string; sentiment: string; suggested_department: string; safety_review_required: boolean;
  safety_flag: string | null; analysis_notice: string
}
export type Post = {
  id: number; content: string; category: string; location: string | null;
  author: { id: number; name: string }; created_at: string; likes: number; comments: number;
  liked_by_me: boolean; can_edit: boolean
}
