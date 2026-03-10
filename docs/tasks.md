# Benchmark Tasks

The repository ships 24 tasks:

- `mobile_drawer_route_close`
- `orders_category_filter`
- `settings_empty_email_validation`
- `customers_empty_state_design_system`
- `dashboard_low_stock_alert`
- `orders_export_preserve_user_note`
- `orders_retry_existing_api_client`
- `theme_label_protected_file_safety`
- `customers_reset_filter_action`
- `customers_growth_segment_filter`
- `customers_loading_notice_visible`
- `dashboard_loading_notice_visible`
- `dashboard_alert_hidden_when_disabled`
- `dashboard_needs_attention_count`
- `orders_export_filtered_slice`
- `orders_retry_preserves_selected_category`
- `orders_error_state_retry_action`
- `orders_export_totals_two_decimals`
- `settings_invalid_email_format`
- `settings_success_trims_email`
- `settings_success_clears_error`
- `settings_input_clears_after_success`
- `theme_light_label_correct`
- `theme_dark_label_correct`

Each task spec defines:

- `task_id`
- `title`
- `prompt_file`
- `setup_patch`
- `expected_files`
- `allowed_files`
- `forbidden_files`
- `required_validations`
- `forbidden_commands`
- `completion_checks`
- `clarification_allowed`
- `diff_limits`
- optional `seed_user_changes_patch`
- optional `disallowed_code_patterns`
- optional `protected_overrides`

## Task Validator Pattern

Each task has a focused `*.benchmark.test.tsx` validator in the web app:

- `AppShell.benchmark.test.tsx`
- `OrdersPage.benchmark.test.tsx`
- `CustomersPage.benchmark.test.tsx`
- `DashboardPage.benchmark.test.tsx`
- `SettingsPage.benchmark.test.tsx`

The benchmark task config points at a targeted test name or benchmark test file, plus `pnpm --dir web typecheck`.

## Dirty Worktree Scenario

`orders_export_preserve_user_note` applies both:

- a regression patch that breaks the CSV headers
- a separate seeded user-change patch on `web/src/features/orders/OrdersPage.tsx`

The preserve-user-changes detector verifies that seeded file remains untouched after the agent run.

## Coverage Intent

The task set is intentionally redundant across features so each rule is stressed more than once:

- shell/navigation behavior
- orders controller, retry, and export behavior
- settings validation and theme-label behavior
- customers filtering and empty-state behavior
- dashboard loading and alert-state behavior
