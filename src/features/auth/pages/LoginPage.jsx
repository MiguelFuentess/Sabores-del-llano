import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  getRememberedUsername,
  loginWithCredentials,
} from '../services/authService.js';

function UserIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.5 20.1a7.5 7.5 0 0 1 15 0A17.9 17.9 0 0 1 12 21.75c-2.68 0-5.22-.58-7.5-1.65Z" /></svg>;
}

function LockIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>;
}

function EyeIcon({ hidden }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.04 12.32a1 1 0 0 1 0-.64A10.5 10.5 0 0 1 12 4.5a10.5 10.5 0 0 1 9.96 7.18 1 1 0 0 1 0 .64A10.5 10.5 0 0 1 12 19.5a10.5 10.5 0 0 1-9.96-7.18Z" />{hidden ? <><path d="m4 4 16 16" /><path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" /></> : <circle cx="12" cy="12" r="3" />}</svg>;
}

export default function LoginPage() {
  const [username, setUsername] = useState(() => getRememberedUsername());
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberCredentials, setRememberCredentials] = useState(() => Boolean(getRememberedUsername()));
  const [rememberAnimation, setRememberAnimation] = useState('');
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;

    const nextErrors = {};
    if (!username.trim()) nextErrors.username = 'Ingresa tu correo o usuario.';
    if (!password) nextErrors.password = 'Ingresa tu contraseña.';
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setIsSubmitting(true);
    try {
      await loginWithCredentials({
        username,
        password,
        rememberCredentials,
      });
      const destination = location.state?.from?.pathname?.startsWith('/app')
        ? location.state.from.pathname
        : '/app/dashboard';
      navigate(destination, { replace: true });
    } catch (loginError) {
      setErrors({
        general: loginError.message || 'No fue posible iniciar sesión.',
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return <main className="login-page">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-card__inner">
        <header className="login-header">
          <h1 id="login-title">Iniciar Sesión</h1>
          <p>Ingrese sus credenciales de acceso</p>
        </header>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-field">
            <label htmlFor="username">Correo o Usuario</label>
            <div className={`login-input-wrap${errors.username ? ' login-input-wrap--error' : ''}`}>
              <span className="login-input-icon"><UserIcon /></span>
              <input id="username" name="username" type="text" autoComplete="username" placeholder="usuario@ejemplo.com" value={username} onChange={(event) => { setUsername(event.target.value); setErrors((current) => ({ ...current, username: '', general: '' })); }} aria-invalid={Boolean(errors.username)} aria-describedby={errors.username ? 'username-error' : undefined} />
            </div>
            {errors.username && <p className="login-field-error" id="username-error" role="alert">{errors.username}</p>}
          </div>

          <div className="login-field">
            <label htmlFor="password">Contraseña de Seguridad</label>
            <div className={`login-input-wrap${errors.password ? ' login-input-wrap--error' : ''}`}>
              <span className="login-input-icon"><LockIcon /></span>
              <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="••••••••••••" value={password} onChange={(event) => { setPassword(event.target.value); setErrors((current) => ({ ...current, password: '', general: '' })); }} aria-invalid={Boolean(errors.password)} aria-describedby={errors.password ? 'password-error' : undefined} />
              <button className="login-password-toggle" type="button" aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}><EyeIcon hidden={showPassword} /></button>
            </div>
            {errors.password && <p className="login-field-error" id="password-error" role="alert">{errors.password}</p>}
          </div>

          {errors.general && <p className="login-field-error" id="login-general-error" role="alert">{errors.general}</p>}

          <div className="login-remember">
            <style>{`
              @keyframes remember-check-on { from { opacity: .45; } to { opacity: 1; } }
              @keyframes remember-check-off { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
              .login-remember__checkbox { transition: accent-color 180ms ease; }
              .login-remember__checkbox--on { animation: remember-check-on 180ms ease-out; }
              .login-remember__checkbox--off { animation: remember-check-off 180ms ease-out; }
              @media (prefers-reduced-motion: reduce) {
                .login-remember__checkbox { transition: none; }
                .login-remember__checkbox--on, .login-remember__checkbox--off { animation: none; }
              }
            `}</style>
            <input
              id="remember-me"
              name="remember-me"
              type="checkbox"
              className={`login-remember__checkbox${rememberAnimation ? ` ${rememberAnimation}` : ''}`}
              checked={rememberCredentials}
              onChange={(event) => {
                const checked = event.target.checked;
                setRememberCredentials(checked);
                setRememberAnimation(checked ? 'login-remember__checkbox--on' : 'login-remember__checkbox--off');
              }}
              aria-describedby="remember-note"
            />
            <label htmlFor="remember-me">Recordar credenciales de acceso</label>
            <span className="login-tooltip" id="remember-note">Guarda el usuario y mantiene activa la sesión sin almacenar tu contraseña.</span>
          </div>

          <div className="login-submit-wrap">
            <button className="login-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Verificando acceso...' : 'Ingresar al Panel Administrativo'}
            </button>
          </div>
        </form>

        <footer className="login-footer">
          <p>Uso únicamente para personal autorizado de Sabores del Llano, Tradición culinaria.</p>

        </footer>
      </div>
    </section>
  </main>;
}
