# Implementation roadmap

1. Foundation: offline desktop UI, local database, module registry, privacy tests.
2. My Finance: monthly invested/current values for Stocks, Mutual Funds, FD, and
   RD; entry/edit UI; month/year history rows; calendar-month comparisons.
   Includes explicit entry-period controls and an offline comparison graph with
   independent show/hide controls for every balance and difference field.
3. Users: name-only profile creation, user-scoped monthly records, one dropdown
   for entry/history/graphs, read-only ALL sums, and combined monthly summaries.
   Automatic MoM uses the same reporting users in adjacent months; differences
   remain unknown when snapshots are missing.
4. Implement subsequent user-defined menus with synthetic test data, verify
   locally, and commit and publish only source and documentation to GitHub.
5. Repeat for each subsequent menu. Never publish application data.

Current interpretation: monthly amounts are portfolio snapshots in INR. Both
invested and current differences are calculated for each asset against the
previous calendar month. Missing comparison months display a dash.
