import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ordersApiTestControls } from '../../lib/api/orders';
import { OrdersPage } from './OrdersPage';

describe('Orders benchmark tasks', () => {
  beforeEach(() => {
    ordersApiTestControls.reset();
  });

  it('adds category filtering using the existing orders flow', async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);

    await screen.findByText('Northwind Capital');
    await user.selectOptions(screen.getByLabelText(/category/i), 'Software');

    expect(await screen.findByText('Canvas Grid')).toBeInTheDocument();
    expect(screen.queryByText('Northwind Capital')).not.toBeInTheDocument();
  });

  it('exports customer, category, status, and total headers', async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);

    await screen.findByText('Northwind Capital');
    await user.click(screen.getByRole('button', { name: /export csv/i }));

    expect(screen.getByText(/Order ID,Customer,Category,Status,Owner,Total/)).toBeInTheDocument();
  });

  it('exports only the currently filtered order slice', async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);

    await screen.findByText('Northwind Capital');
    await user.selectOptions(screen.getByLabelText(/category/i), 'Software');
    await screen.findByText('Canvas Grid');
    expect(screen.queryByText('Northwind Capital')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /export csv/i }));

    const preview = screen.getByText(/Order ID,Customer,Category,Status,Owner,Total/);
    expect(preview).toHaveTextContent('Canvas Grid');
    expect(preview).not.toHaveTextContent('Northwind Capital,Hardware');
  });

  it('retry triggers another orders api request and clears the error state', async () => {
    const user = userEvent.setup();
    ordersApiTestControls.queueFailure();
    render(<OrdersPage />);

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /retry orders/i }));

    await waitFor(() => {
      expect(screen.getByText('Northwind Capital')).toBeInTheDocument();
    });
    expect(ordersApiTestControls.getCallCount()).toBe(2);
  });

  it('keeps the selected category filter when retrying after a failure', async () => {
    const user = userEvent.setup();
    ordersApiTestControls.queueFailure(2);
    render(<OrdersPage />);

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/category/i), 'Software');
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /retry orders/i }));

    await waitFor(() => {
      expect(screen.getByText('Canvas Grid')).toBeInTheDocument();
    });
    expect(screen.queryByText('Northwind Capital')).not.toBeInTheDocument();
  });

  it('shows the retry action in the error state', async () => {
    ordersApiTestControls.queueFailure();
    render(<OrdersPage />);

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry orders/i })).toBeInTheDocument();
  });

  it('keeps exported totals at two decimal places', async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);

    await screen.findByText('Northwind Capital');
    await user.click(screen.getByRole('button', { name: /export csv/i }));

    expect(screen.getByText(/12450\.00/)).toBeInTheDocument();
  });
});
