"""
tests.py

Unit tests for toggl-cli.

Usage: python tests.py [CLASSNAME[.METHODNAME]]

NB: These tests add and modify entries in your toggl account. All of the
entries have the prefix given below, and they should all be removed after
the tests are complete.
"""
PREFIX = "unittest_"

import datetime
import unittest
import pytz
import time
import toggl


def desc(description):
    return "%s%s" % (PREFIX, description)

#----------------------------------------------------------------------------
# TestClientList
#----------------------------------------------------------------------------
class TestClientList(unittest.TestCase):
    
    def setUp(self):
        self.list = toggl.ClientList()
    
    def test_iterator(self):
        num_clients = len(self.list.client_list)
        count = 0
        for client in self.list:
            count += 1
        self.assertEquals(count, num_clients)

#----------------------------------------------------------------------------
# TestDateAndTime
#----------------------------------------------------------------------------
class TestDateAndTime(unittest.TestCase):

    def setUp(self):
        self.dat = toggl.DateAndTime()

    def test_duration_since_epoch(self):
        # one hour into the epoch
        dt = datetime.datetime(1970,1,1,1,0,0,0,tzinfo=pytz.UTC)
        self.assertEquals( self.dat.duration_since_epoch(dt), 3600)

    def test_duration_str_to_seconds(self):
        # one element
        self.assertEquals(self.dat.duration_str_to_seconds("1"), 1)
        # two elements
        self.assertEquals(self.dat.duration_str_to_seconds("1:1"), 61)
        # three elements
        self.assertEquals(self.dat.duration_str_to_seconds("1:1:1"), 3661)

#----------------------------------------------------------------------------
# TestProjectList
#----------------------------------------------------------------------------
class TestProjectList(unittest.TestCase):
    
    def setUp(self):
        self.list = toggl.ProjectList()
 
    def test_iterator(self):
        num_projects = len(self.list.project_list)
        count = 0
        for client in self.list:
            count += 1
        self.assertEquals(count, num_projects)

    def test_find_by_id(self):
        # invalid id's return None
        self.assertIsNone( self.list.find_by_id(-1) )

        # otherwise, we get a project object back
        id = self.list.project_list[0]['id']
        self.assertEquals( self.list.find_by_id(id)['id'], id )

    def test_find_by_name(self):
        # invalid names return None
        self.assertIsNone( self.list.find_by_name('XYZ') )

        # grab first three characters of the first project name
        prefix = self.list.project_list[0]['name'][0:3]
        self.assertEquals( self.list.find_by_name(prefix)['name'][0:3], prefix )

#----------------------------------------------------------------------------
# TestTimeEntry
#----------------------------------------------------------------------------
class TestTimeEntry(unittest.TestCase):

    def setUp(self):
        self.entry = toggl.TimeEntry()
        # force timezone to be UTC
        toggl.DateAndTime.tz = pytz.UTC

    def find_time_entry(self, description):
        return toggl.TimeEntryList().reload().find_by_description(description)

    def mock_time_time(self):
        """Mock time.time()"""
        return 10

    def test_add(self):
        # time entry has no data, raises an exception
        self.assertRaises(Exception, self.entry.add)

        # create basic entry and add it
        start_time = toggl.DateAndTime().now()
        self.entry = toggl.TimeEntry(description=desc('add'), 
            start_time=start_time, duration=10)
        self.entry.add()

        # make sure it shows up in the list
        entry = self.find_time_entry(desc('add'))
        self.assertIsNotNone(entry)
        self.assertEquals(entry.get('duration'), 10)

    def test_continue_from_today(self):
        # create a completed time today
        now = datetime.datetime.utcnow().isoformat()
        toggl.CLI()._add_time_entry([desc('continue2'), now, 'd1:0:0'])

        # find it
        entry = self.find_time_entry(desc('continue2'))
        self.assertIsNotNone(entry)

        # continue it
        entry.continue_entry()

        # find it again, this time, it should be running.
        entry = self.find_time_entry(desc('continue2'))
        self.assertTrue(int(entry.get('duration')) < 0)


    def test_continue_from_yesterday(self):
        # create a completed time yesterday
        yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
        toggl.CLI()._add_time_entry([desc('continue'), yesterday, 'd1:0:0'])

        # find it
        entry = self.find_time_entry(desc('continue'))
        self.assertIsNotNone(entry)

        # continue it
        entry.continue_entry()

        # find the new one
        entry2 = self.find_time_entry(desc('continue'))
        self.assertNotEqual(entry.get('duration'), entry2.get('duration'))

    def test_delete(self):
        # start a time entry
        self.entry = toggl.TimeEntry(description=desc('delete'))
        self.entry.start()

        # deleting an entry without an id is an error
        self.assertRaises(Exception, self.entry.delete)

        # make sure it shows up in the list, this also fetches the id
        entry = self.find_time_entry(desc('delete'))
        self.assertIsNotNone(entry)

        # delete it
        entry.delete()

        # make sure it shows up in the list
        entry = self.find_time_entry(desc('delete'))
        self.assertIsNone(entry)

    def test_get(self):
        # test invalid property
        self.assertIsNone( self.entry.get('foobar') )

        # test valid property
        self.assertIsNotNone( self.entry.get('created_with') )

    def test_has(self):
        # test nonexistant property
        self.assertFalse( self.entry.has('foobar') )

        # test existing, but None property
        self.entry.set('foobar', None)
        self.assertFalse( self.entry.has('foobar') )
       
        # test existing, non-None property
        self.entry.set('foobar', True)
        self.assertTrue( self.entry.has('foobar') )

    def test_normalized_duration(self):
        # no duration set, raise an exception
        self.assertRaises(Exception, self.entry.normalized_duration)

        # positive duration
        self.entry.set('duration', 1)
        self.assertEquals( self.entry.normalized_duration(), 1 )

        # negative duration. mock time.time() for this test only.
        self.entry.set('duration', -1)
        old_time = time.time
        time.time = self.mock_time_time
        self.assertEquals( self.entry.normalized_duration(), 9 )
        time.time = old_time

    def test_set(self):
        # basic test
        self.entry.set('foo', 'bar')
        self.assertEquals( self.entry.data['foo'], 'bar' )

        # remove value
        self.entry.set('foo', None)
        self.assertFalse('foo' in self.entry.data)
        
    def test_start_simple(self):
        # test with simpliest entry
        self.entry = toggl.TimeEntry(description=desc('start'))
        self.entry.start()
        orig_start = self.entry.get('start')

        # fetch the entry from toggl and compare with what we created
        entry = self.find_time_entry(desc('start'))
        self.assertIsNotNone(entry)

        # round duration to nearest integer
        #self.assertEqual(entry.get('start'), orig_start)

    def test_start_complex(self):
        # test with preset start time one hour ago UTC
        one_hour_ago = pytz.UTC.localize(datetime.datetime.utcnow() - datetime.timedelta(hours=1))
        self.entry = toggl.TimeEntry(description=desc('start2'),
            start_time=one_hour_ago)
        self.entry.start()
        orig_duration = self.entry.get('duration')

        # see what toggl has
        entry = self.find_time_entry(desc('start2'))
        self.assertIsNotNone(entry)
       
        # toggl duration should be 1 hour
        self.assertGreaterEqual(entry.normalized_duration(), 3600)

    def test_stop_simple(self):
        # empty time entry raises an exception
        self.assertRaises(Exception, self.entry.stop)

        # non-running entry raises an exception
        self.entry.set('duration', 10)
        self.assertRaises(Exception, self.entry.stop)

        # missing an id raises an exception
        self.entry.set('duration', -10)
        self.assertRaises(Exception, self.entry.stop)

        # start an entry now
        self.entry = toggl.TimeEntry(description=desc('stop'))
        self.entry.start()

        # find it 
        entry = self.find_time_entry(desc('stop'))
        self.assertIsNotNone(entry)

        # stop it
        entry.stop()

        # find it again
        entry = self.find_time_entry(desc('stop'))

        # make sure duration is positive. we can't be more specific because
        # we don't know the lag between us and toggl.
        self.assertGreaterEqual(entry.get('duration'), 0)

    def test_stop_complex(self):
        # start an entry now
        self.entry = toggl.TimeEntry(description=desc('stop2'))
        self.entry.start()

        # find it
        entry = self.find_time_entry(desc('stop2'))
        self.assertIsNotNone(entry)
        
        # stop it an hour from now
        one_hour_ahead = pytz.UTC.localize(datetime.datetime.utcnow() + datetime.timedelta(hours=1))
        entry.stop(one_hour_ahead)

        # find it again
        entry = self.find_time_entry(desc('stop2'))
        self.assertIsNotNone(entry)

        # make sure duration is at least 1 hour (3600 seconds)
        self.assertGreaterEqual(entry.get('duration'), 3600)

    def test_validate(self):
        # entry must have 'start', 'duration', and 'description' properties.
        self.assertRaises(Exception, self.entry.validate)
        self.entry.set('start', 'start')
        self.assertRaises(Exception, self.entry.validate)
        self.entry.set('duration', 'duration')
        self.assertRaises(Exception, self.entry.validate)
        self.entry.set('description', 'description')
        self.assertTrue( self.entry.validate() )

#----------------------------------------------------------------------------
# TestTimeEntryList
#----------------------------------------------------------------------------
class TestTimeEntryList(unittest.TestCase):
    
    def setUp(self):
        self.list = toggl.TimeEntryList()

    def test_find_by_description(self):
        toggl.CLI()._start_time_entry([desc('find_by_description')])
        self.list.reload()

        # searching for something that doesn't exist returns none
        self.assertIsNone( self.list.find_by_description('foobar') )

        # otherwise, we get an entry with the matching description
        entry1 = self.list.find_by_description(desc('find_by_description'))
        self.assertEquals( entry1.get('description'), desc('find_by_description'))

        # start another entry with the same description
        toggl.CLI()._start_time_entry([desc('find_by_description')])
        self.list.reload()

        # searching should return the newer entry
        entry2 = self.list.find_by_description(desc('find_by_description'))
        #self.assertNotEquals( entry1.get('start'), entry2.get('start') )
 
    def test_iterator(self):
        num_entries = len(self.list.time_entries)
        count = 0
        for client in self.list:
            count += 1
        self.assertEquals(count, num_entries) 

    def test_now(self):
        # test with no entries running
        toggl.CLI()._stop_time_entry([])
        self.list.reload()
        self.assertIsNone( self.list.now() )

        # test with running entry
        toggl.CLI()._start_time_entry([desc('now')])
        self.list.reload()
        current = self.list.now()
        self.assertIsNotNone(current)
        self.assertEquals( current.get('description'), desc('now') )
        current.stop()

def tearDownModule():
    """
    Cleans up toggl with all the unittest entries we just created. This
    relies on TimeEntryList and TimeEntry.delete.
    """
    print "Removing toggl entries created by the test..."
    for entry in toggl.TimeEntryList():
        if entry.get('description') is not None and entry.get('description').startswith('unittest_'):
            entry.delete()

if __name__ == '__main__':
    toggl.CLI() # this initializes Logger to INFO
    #toggl.Logger.level = toggl.Logger.DEBUG
    toggl.Logger.level = toggl.Logger.NONE
    unittest.main()
