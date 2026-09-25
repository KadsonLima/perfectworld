"""Control-flow tests; no live territory or bid mutations."""
import unittest
from unittest.mock import patch
import pw_admin as app


class BidTests(unittest.TestCase):
    def test_country_battle_is_not_tw(self):
        self.assertEqual(app.bid_evidence('CountryBattle System Change State 0---->1.'), (None, None))

    def test_native_evidence(self):
        self.assertEqual(app.bid_evidence('Timer update: (327601) Wed\nx: beginbid:zoneid=1:now=1'), (327601, 1))
        self.assertEqual(app.bid_evidence('beginbid:zoneid=1\nendbid:zoneid=1'), (None, 0))

    def run_control(self, action, logs, before=None, cities=None, ticks=None):
        def docker(*args, **kwargs):
            if args[0] == 'exec':
                return next(iter(app.DELIVERY_HASHES)) + ' /home/gdeliveryd'
            return logs
        with patch.object(app, 'delivery_boot', return_value='boot'), \
             patch.object(app, 'docker', side_effect=docker), \
             patch.object(app, 'tw_status', return_value=before or {'mode': 'auto', 'state': 0}), \
             patch.object(app, 'table', return_value=cities or []), \
             patch.object(app, 'audit') as audit, \
             patch.object(app, 'debug') as debug, \
             patch.object(app.Path, 'exists', return_value=False), \
             patch.object(app.time, 'monotonic', side_effect=ticks or [0, 0]), \
             patch.object(app.time, 'sleep'):
            result = app.control_bids({'action': action})
            return result, debug.call_args_list, audit.call_args_list

    def test_open_requires_native_transition(self):
        with self.assertRaisesRegex(ValueError, 'sem confirmacao'):
            self.run_control('open', 'Timer update: (327601)', ticks=[0, 0, 81])

    def test_open_confirmed(self):
        result, calls, _ = self.run_control('open', 'Timer update: (327601)\nbeginbid:zoneid=1')
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0].args, ('bidtime', '327601'))

    def test_close_confirmed(self):
        result, calls, _ = self.run_control('close', 'Timer update: (416521)\nendbid:zoneid=1', {'mode': 'open', 'state': 1})
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0].args, ('bidtime', '416521'))

    def test_auto_confirmed(self):
        result, calls, _ = self.run_control('auto', 'Timer update: (0)', {'mode': 'close', 'state': 0})
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0].args, ('bidtime', '0'))

    def test_existing_dispute_blocks_reopening(self):
        with self.assertRaisesRegex(ValueError, 'disputa'):
            self.run_control('open', '', cities=[{'challenger': '1', 'status': '0'}])

    def test_invalid_action_never_calls_server(self):
        with patch.object(app, 'docker') as docker:
            with self.assertRaises(ValueError):
                app.control_bids({'action': 'arbitrary'})
            docker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
