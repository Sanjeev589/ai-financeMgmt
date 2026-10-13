import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from finance_app.modules.finance import ASSETS, MONTHS, FinanceStore
from finance_app.modules.finance_graph import FinanceGraph, GraphPoint, axis_range, make_series, segments
from finance_app.modules.my_finance import MyFinanceView
from finance_app.storage import Database
from finance_app.modules.users import UserStore


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.user = UserStore(self.database).add("Synthetic user")
        self.store = FinanceStore(self.database, self.user.id)
        self.store.save_month(2025, 12, {asset: (10000, 15000) for asset, _ in ASSETS})
        self.store.save_month(2026, 1, {asset: (12000, 14000) for asset, _ in ASSETS})
        self.store.save_month(2026, 3, {asset: (18000, 21000) for asset, _ in ASSETS})

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def test_entered_fields_are_exact_and_ordered_by_month_and_year(self):
        selected = {f"{asset}_{metric}" for asset, _ in ASSETS for metric in ("invested", "current")}
        lines = make_series(self.store.history(), selected)
        self.assertEqual(len(lines), 8)
        line = next(line for line in lines if line.key == "stocks_current")
        self.assertEqual([(point.year, point.month, point.amount) for point in line.points], [(2025, 12, 15000), (2026, 1, 14000), (2026, 3, 21000)])

    def test_toggling_one_field_only_removes_that_series(self):
        lines = make_series(self.store.history(), {"stocks_current", "rd_invested"})
        self.assertEqual({line.key for line in lines}, {"stocks_current", "rd_invested"})
        self.assertEqual(len(make_series(self.store.history(), {"rd_invested"})), 1)
        self.assertEqual(make_series(self.store.history(), set()), ())
        self.assertEqual(self.store.get_month(2026, 1).balances[0].current, 14000)

    def test_missing_mom_is_not_zero_and_negative_changes_are_retained(self):
        line = make_series(self.store.history(), {"stocks_current_diff"})[0]
        self.assertEqual([point.amount for point in line.points], [None, -1000, None])
        self.assertEqual(len(segments(line.points)), 1)
        self.assertEqual(segments(line.points)[0][0].month, 1)

    def test_lines_break_at_gaps_and_unknown_points(self):
        line = make_series(self.store.history(), {"stocks_current"})[0]
        self.assertEqual([len(segment) for segment in segments(line.points)], [2, 1])
        points = (GraphPoint(2026, 1, 0), GraphPoint(2026, 2, None), GraphPoint(2026, 3, 100))
        self.assertEqual([len(segment) for segment in segments(points)], [1, 1])

    def test_scale_handles_negative_zero_single_and_large_values(self):
        for values in ((0,), (1,), (-1000, 550), (-100,), (99999999999999,)):
            with self.subTest(values=values):
                low, high, step = axis_range(values)
                self.assertLess(low, high)
                self.assertLessEqual(low, min(values))
                self.assertGreaterEqual(high, max(values))
                self.assertLessEqual(low, 0)
                self.assertGreaterEqual(high, 0)
                self.assertLessEqual(len(range(low, high + 1, step)), 8)

    def test_graph_reflects_saved_updates(self):
        self.store.save_month(2026, 1, {asset: (13000, 19000) for asset, _ in ASSETS})
        line = make_series(self.store.history(), {"stocks_current"})[0]
        self.assertEqual(line.points[1].amount, 19000)

    def make_renderer(self, enabled):
        # Record actual Canvas draw calls without a desktop display. This tests
        # the rendering path, not fonts or visual layout on a target OS.
        graph = FinanceGraph.__new__(FinanceGraph)
        graph.canvas = Mock()
        graph.canvas.winfo_width.return_value = 800
        graph.canvas.winfo_height.return_value = 320
        graph.pending_redraw = None
        graph.hit_points = []
        graph.hint = "Hover for details"
        graph.hover_text = Mock()
        graph.history = self.store.history()
        graph.scope_name = "Synthetic user"
        graph.enabled = {key: Mock(get=Mock(return_value=True)) for key in enabled}
        return graph

    def test_render_and_hover_show_the_selected_field_and_exact_month(self):
        graph = self.make_renderer({"stocks_current"})
        graph.draw()
        self.assertEqual(len(graph.hit_points), 3)
        self.assertEqual(graph.canvas.create_oval.call_count, 3)
        x, y, label, point = graph.hit_points[1]
        graph.hover(Mock(x=x, y=y))
        text = graph.hover_text.set.call_args.args[0]
        self.assertIn("January 2026", text)
        self.assertIn("Stocks — Current", text)
        self.assertIn("₹140.00", text)
        plot_lines = [call for call in graph.canvas.create_line.call_args_list if call.kwargs.get("fill") == "#2563eb"]
        self.assertEqual(len(plot_lines), 1)  # December–January only; March is isolated.

    def test_no_fields_or_no_data_displays_guidance(self):
        graph = self.make_renderer(set())
        graph.draw()
        self.assertEqual(graph.hit_points, [])
        self.assertIn("Select at least", graph.canvas.create_text.call_args.kwargs["text"])
        graph.history = ()
        graph.draw()
        self.assertIn("first monthly entry", graph.canvas.create_text.call_args.kwargs["text"])


class EntryPeriodTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(self.directory.name)
        self.tcl = tk.Tcl()
        self.view = MyFinanceView.__new__(MyFinanceView)
        self.view.parent = None
        self.user = UserStore(self.database).add("Entry test user")
        self.view.store = FinanceStore(self.database, self.user.id)
        self.view.loaded_user_id = self.user.id
        self.view.month = tk.StringVar(master=self.tcl, value=MONTHS[2])
        self.view.year = tk.StringVar(master=self.tcl, value="2024")
        self.view.loaded_period = (2024, 3)
        self.view.status = Mock()
        self.view.save_button = Mock()
        self.view.fields = {asset: (tk.StringVar(master=self.tcl, value="10.25"), tk.StringVar(master=self.tcl, value="20.75")) for asset, _ in ASSETS}
        self.view.refresh_history = Mock()

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def test_entry_values_save_under_the_selected_month_and_year(self):
        self.view.save_month()
        record = self.view.store.get_month(2024, 3)
        self.assertEqual(len(record.balances), 4)
        self.assertTrue(all(balance.invested == 1025 and balance.current == 2075 for balance in record.balances))
        self.assertIsNone(self.view.store.get_month(2026, 3))

    def test_changed_year_disables_saving_and_cannot_reassign_the_form(self):
        self.view.year.set("2025")
        self.view.period_changed()
        self.view.save_button.state.assert_called_with(["disabled"])
        with patch("finance_app.modules.my_finance.messagebox.showerror") as error:
            self.view.save_month()
        error.assert_called_once()
        self.assertIsNone(self.view.store.get_month(2025, 3))
        self.assertEqual(self.view.store.history(), ())

    def test_invalid_period_is_rejected_without_saving(self):
        self.view.year.set("not-a-year")
        self.view.period_changed()
        self.view.save_button.state.assert_called_with(["disabled"])
        with patch("finance_app.modules.my_finance.messagebox.showerror") as error:
            self.view.save_month()
        error.assert_called_once()
        self.assertEqual(self.view.store.history(), ())


if __name__ == "__main__":
    unittest.main()
