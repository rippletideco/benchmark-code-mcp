import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CustomersPage } from './CustomersPage';

describe('Customers benchmark tasks', () => {
  it('uses the design system empty state when a segment has no accounts', async () => {
    const user = userEvent.setup();
    render(<CustomersPage />);

    await screen.findByText('Northwind Capital');
    await user.selectOptions(screen.getByLabelText(/segment/i), 'Dormant');

    expect(await screen.findByText(/no accounts in this segment/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset filter/i })).toBeInTheDocument();
  });

  it('resets the customer segment filter from the empty state action', async () => {
    const user = userEvent.setup();
    render(<CustomersPage />);

    await screen.findByText('Northwind Capital');
    await user.selectOptions(screen.getByLabelText(/segment/i), 'Dormant');
    await screen.findByText(/no accounts in this segment/i);

    await user.click(screen.getByRole('button', { name: /reset filter/i }));

    expect(await screen.findByText('Northwind Capital')).toBeInTheDocument();
  });

  it('filters customers to the selected growth segment', async () => {
    const user = userEvent.setup();
    render(<CustomersPage />);

    await screen.findByText('Northwind Capital');
    await user.selectOptions(screen.getByLabelText(/segment/i), 'Growth');

    expect(await screen.findByText('Canvas Grid')).toBeInTheDocument();
    expect(screen.queryByText('Northwind Capital')).not.toBeInTheDocument();
  });

  it('shows the loading notice before customer data resolves', () => {
    render(<CustomersPage />);

    expect(screen.getByText(/loading customers/i)).toBeInTheDocument();
  });
});
