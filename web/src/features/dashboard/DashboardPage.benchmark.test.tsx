import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProviders } from '../../app/AppProviders';
import { resetSettingsApi, updateSettings } from '../../lib/api/settings';
import { DashboardPage } from './DashboardPage';
import { SettingsPage } from '../settings/SettingsPage';

describe('Dashboard benchmark tasks', () => {
  beforeEach(() => {
    resetSettingsApi();
  });

  it('keeps low-stock alerts in sync with settings', async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <DashboardPage />
        <SettingsPage />
      </AppProviders>
    );

    expect(await screen.findByText(/low-stock alert rail is active/i)).toBeInTheDocument();
    await user.click(screen.getByLabelText(/low-stock alerts/i));
    await waitFor(() => {
      expect(screen.queryByText(/low-stock alert rail is active/i)).not.toBeInTheDocument();
    });
  });

  it('shows the loading notice before preferences resolve', () => {
    render(
      <AppProviders>
        <DashboardPage />
      </AppProviders>
    );

    expect(screen.getByText(/loading operating preferences/i)).toBeInTheDocument();
  });

  it('hides the low-stock alert when the setting starts disabled', async () => {
    await updateSettings({ lowStockAlerts: false });
    render(
      <AppProviders>
        <DashboardPage />
      </AppProviders>
    );

    expect(await screen.findByText(/steer the queue before stock tension becomes churn/i)).toBeInTheDocument();
    expect(screen.queryByText(/low-stock alert rail is active/i)).not.toBeInTheDocument();
  });

  it('shows the expected needs attention metric', async () => {
    render(
      <AppProviders>
        <DashboardPage />
      </AppProviders>
    );

    expect(await screen.findByText('Needs attention')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
