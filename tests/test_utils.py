import datetime
import unittest

import pytz

from toggl import utils


# ----------------------------------------------------------------------------
# TestDateAndTime
# ----------------------------------------------------------------------------
class TestDateAndTime(unittest.TestCase):

    def setUp(self):
        self.dat = utils.DateAndTime()

    def test_duration_since_epoch(self):
        # one hour into the epoch
        dt = datetime.datetime(1970, 1, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
        self.assertEquals(self.dat.duration_since_epoch(dt), 3600)

    def test_duration_str_to_seconds(self):
        # one element
        self.assertEquals(self.dat.duration_str_to_seconds("1"), 1)
        # two elements
        self.assertEquals(self.dat.duration_str_to_seconds("1:1"), 61)
        # three elements
        self.assertEquals(self.dat.duration_str_to_seconds("1:1:1"), 3661)
