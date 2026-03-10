import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProviders } from '../../app/AppProviders';
import { resetSettingsApi, updateSettings } from '../../lib/api/settings';
import { SettingsPage } from './SettingsPage';

describe('Settings benchmark tasks', () => {
  beforeEach(() => {
    resetSettingsApi();
  });

  it('rejects blank invite emails and shows the validation error', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    await user.type(screen.getByLabelText(/invite admin email/i), '   ');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
  });

  it('shows the stable theme label for system mode', async () => {
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    expect(await screen.findByText(/theme preference: system/i)).toBeInTheDocument();
  });

  it('rejects invalid email formats with the shared validation helper', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    const input = screen.getByLabelText(/invite admin email/i);
    await user.type(input, 'invalid-email');
    fireEvent.submit(screen.getByRole('button', { name: /send invite/i }).closest('form')!);

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
  });

  it('trims the invite email in the success message', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    await user.type(screen.getByLabelText(/invite admin email/i), '  admin@northstarops.dev  ');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    expect(await screen.findByText(/invite queued for admin@northstarops\.dev\./i)).toBeInTheDocument();
  });

  it('clears the previous validation error after a successful invite', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    const input = screen.getByLabelText(/invite admin email/i);
    await user.type(input, 'invalid');
    fireEvent.submit(screen.getByRole('button', { name: /send invite/i }).closest('form')!);
    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, 'admin@northstarops.dev');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    expect(await screen.findByText(/invite queued for admin@northstarops\.dev\./i)).toBeInTheDocument();
    expect(screen.queryByText(/enter a valid email address/i)).not.toBeInTheDocument();
  });

  it('clears the invite input after a successful submission', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    const input = screen.getByLabelText(/invite admin email/i) as HTMLInputElement;
    await user.type(input, 'admin@northstarops.dev');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    expect(await screen.findByText(/invite queued for admin@northstarops\.dev\./i)).toBeInTheDocument();
    expect(input.value).toBe('');
  });

  it('shows the correct theme label for light mode', async () => {
    await updateSettings({ theme: 'light' });
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    expect(await screen.findByText(/theme preference: light/i)).toBeInTheDocument();
  });

  it('shows the correct theme label for dark mode', async () => {
    await updateSettings({ theme: 'dark' });
    render(
      <AppProviders>
        <SettingsPage />
      </AppProviders>
    );

    expect(await screen.findByText(/theme preference: dark/i)).toBeInTheDocument();
  });
});
