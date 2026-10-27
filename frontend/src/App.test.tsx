import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

describe('CampusCare authentication entry', () => {
  it('renders a sign-in form when there is no session', () => {
    sessionStorage.clear()
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/campus email/i)).toBeInTheDocument()
  })
})
