# Implementation roadmap

1. Foundation: offline desktop UI, local database, module registry, privacy tests.
2. My Finance: monthly invested/current values for Stocks, Mutual Funds, FD, and
   RD; entry/edit UI; month/year history rows; calendar-month comparisons.
   Includes explicit entry-period controls and an offline comparison graph with
   independent show/hide controls for every balance and difference field.
3. Implement subsequent user-defined menus with synthetic test data, verify
   locally, and commit and publish only source and documentation to GitHub.
4. Repeat for each subsequent menu. Never publish application data.

Current interpretation: monthly amounts are portfolio snapshots in INR. Both
invested and current differences are calculated for each asset against the
previous calendar month. Missing comparison months display a dash.
