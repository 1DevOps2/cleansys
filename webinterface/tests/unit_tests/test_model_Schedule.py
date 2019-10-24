from django.test import TestCase
from webinterface.models import *

import logging
from unittest.mock import *


class ScheduleQuerySetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Schedule
        cls.enabled = Schedule.objects.create(name="enabled", disabled=False)
        cls.disabled = Schedule.objects.create(name="disabled", disabled=True)

    def test__enabled(self):
        enabled_schedules = Schedule.objects.enabled()
        self.assertIn(self.enabled, enabled_schedules)
        self.assertNotIn(self.disabled, enabled_schedules)

    def test__disabled(self):
        disabled_schedules = Schedule.objects.disabled()
        self.assertIn(self.disabled, disabled_schedules)
        self.assertNotIn(self.enabled, disabled_schedules)


class ScheduleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Config
        cls.reference_datetime = datetime.datetime(2010, 1, 8)
        cls.reference_date = correct_dates_to_due_day(cls.reference_datetime.date())
        cls.one_week = timezone.timedelta(days=7)

        # Schedule
        cls.schedule = Schedule.objects.create(name="schedule", cleaners_per_date=3)
        cls.no_assignment_schedule = Schedule.objects.create(name="no_assignment_sch", cleaners_per_date=2, frequency=2)

        # ScheduleGroup
        cls.group = ScheduleGroup.objects.create(name="group")
        cls.group.schedules.add(cls.schedule, cls.no_assignment_schedule)

        # Cleaners
        cls.cleaner1 = Cleaner.objects.create(name="cleaner1", preference=1)
        cls.cleaner2 = Cleaner.objects.create(name="cleaner2", preference=1)
        cls.cleaner3 = Cleaner.objects.create(name="cleaner3")

        # CleaningDays
        cls.cleaning_day1 = CleaningDay.objects.create(
            date=correct_dates_to_due_day(cls.reference_date), schedule=cls.schedule)
        cls.cleaning_day2 = CleaningDay.objects.create(date=correct_dates_to_due_day(
            cls.reference_date + cls.one_week), schedule=cls.schedule)
        cls.cleaning_day3 = CleaningDay.objects.create(date=correct_dates_to_due_day(
            cls.reference_date + 2 * cls.one_week), schedule=cls.schedule)

        # Affiliations
        cls.cleaner1_affiliation = Affiliation.objects.create(
            cleaner=cls.cleaner1, group=cls.group, beginning=cls.reference_date,
            end=cls.reference_date + 3 * cls.one_week)
        cls.cleaner2_affiliation = Affiliation.objects.create(
            cleaner=cls.cleaner2, group=cls.group, beginning=cls.reference_date,
            end=cls.reference_date + 3 * cls.one_week)

        # Assignments
        cls.assignment1 = Assignment.objects.create(
            cleaner=cls.cleaner1, schedule=cls.schedule, cleaning_day=cls.cleaning_day1)
        cls.assignment2 = Assignment.objects.create(
            cleaner=cls.cleaner2, schedule=cls.schedule, cleaning_day=cls.cleaning_day1)
        cls.assignment3 = Assignment.objects.create(
            cleaner=cls.cleaner2, schedule=cls.schedule, cleaning_day=cls.cleaning_day2)
        cls.assignment4 = Assignment.objects.create(
            cleaner=cls.cleaner2, schedule=cls.schedule, cleaning_day=cls.cleaning_day2)

        # DutySwitch Requests
        cls.rejected_dutyswitch = DutySwitch.objects.create(status=2, source_assignment=cls.assignment1)
        cls.dutyswitch_request_received = DutySwitch.objects.create(source_assignment=cls.assignment2,
                                                                    selected_assignment=cls.assignment1)
        cls.pending_dutyswitch_request = DutySwitch.objects.create(status=1, source_assignment=cls.assignment1)

    def test__creation(self):
        schedule = Schedule.objects.create()
        self.assertIsInstance(schedule, Schedule)
        self.assertEqual(schedule.slug, slugify(schedule.name))

    def test__str(self):
        self.assertEqual(self.schedule.__str__(), self.schedule.name)

    def test__deployment_ratios__no_cleaners(self):
        schedule = Schedule()
        self.assertListEqual(schedule.deployment_ratios(self.reference_date), [])

    def test__deployment_ratios__cleaners_have_no_assignments(self):
        container = self.no_assignment_schedule.deployment_ratios(self.reference_date)

        self.assertIn([self.cleaner1, 0], container)
        self.assertIn([self.cleaner2, 0], container)
        self.assertEqual(len(container), 2)

    def test__deployment_ratios(self):
        ratios = self.schedule.deployment_ratios(self.cleaning_day1.date)
        self.assertIn([self.cleaner1, 1/4], ratios)
        self.assertIn([self.cleaner2, 3/4], ratios)
        self.assertEqual(len(ratios), 2)

    def test__defined_on_date(self):
        weekly_schedule = Schedule(frequency=1)
        even_week_schedule = Schedule(frequency=2)
        odd_week_schedule = Schedule(frequency=3)

        even_week = datetime.date(2010, 2, 8)
        odd_week = datetime.date(2010, 2, 1)

        self.assertTrue(weekly_schedule.defined_on_date(even_week))
        self.assertTrue(even_week_schedule.defined_on_date(even_week))
        self.assertFalse(odd_week_schedule.defined_on_date(even_week))

        self.assertFalse(even_week_schedule.defined_on_date(odd_week))
        self.assertTrue(odd_week_schedule.defined_on_date(odd_week))

    def test__new_cleaning_duties__keep_existing_assignments(self):
        date1, date2 = [self.reference_date, self.reference_date + 4 * self.one_week]

        with patch.object(Schedule, 'create_assignment', return_value=False) as mock_create_assignment:
            self.schedule.new_cleaning_duties(date2, date1, 2)
            new_assignment_set = self.schedule.assignment_set.all()
            self.assertIn(self.assignment1, new_assignment_set)
            self.assertIn(self.assignment2, new_assignment_set)
            self.assertIn(self.assignment3, new_assignment_set)
            self.assertIn(self.assignment4, new_assignment_set)

            self.assertListEqual(mock_create_assignment.mock_calls,
                                 [call(date1), call(date1 + self.one_week), call(date1 + 2 * self.one_week),
                                  call(date1 + 3 * self.one_week), call(date1 + 4 * self.one_week)])

    def test__new_cleaning_duties__clear_existing_assignments(self):
        date1, date2 = [self.reference_date, self.reference_date + 4 * self.one_week]

        with patch.object(Schedule, 'create_assignment', return_value=False) as mock_create_assignment:
            self.schedule.new_cleaning_duties(date2, date1, 1)
            new_assignment_set = self.schedule.assignment_set.all()
            self.assertNotIn(self.assignment1, new_assignment_set)
            self.assertNotIn(self.assignment2, new_assignment_set)
            self.assertNotIn(self.assignment3, new_assignment_set)
            self.assertNotIn(self.assignment4, new_assignment_set)
            self.assertListEqual(mock_create_assignment.mock_calls,
                                 [call(date1), call(date1 + self.one_week), call(date1 + 2 * self.one_week),
                                  call(date1 + 3 * self.one_week), call(date1 + 4 * self.one_week)])

    def test__new_cleaning_duties__only_reassign_existing(self):
        date1, date2 = [self.reference_date, self.reference_date + 4 * self.one_week]

        with patch.object(Schedule, 'create_assignment', return_value=False) as mock_create_assignment:
            self.schedule.new_cleaning_duties(date2, date1, 3)
            new_assignment_set = self.schedule.assignment_set.all()
            self.assertNotIn(self.assignment1, new_assignment_set)
            self.assertNotIn(self.assignment2, new_assignment_set)
            self.assertNotIn(self.assignment3, new_assignment_set)
            self.assertNotIn(self.assignment4, new_assignment_set)
            self.assertListEqual(mock_create_assignment.mock_calls,
                                 [call(date1), call(date1 + self.one_week)])

    def test__new_cleaning_duties__invalid_mode(self):
        date1, date2 = [self.reference_date, self.reference_date + 4 * self.one_week]
        with self.assertRaises(OperationalError):
            self.schedule.new_cleaning_duties(date1, date2, mode=4)

    def test__create_assignment__not_defined_on_date(self):
        even_week_schedule = Schedule(frequency=2)
        odd_week = datetime.date(2010, 2, 15)
        self.assertFalse(even_week_schedule.create_assignment(odd_week))

    def test__create_assignment__no_positions_to_fill(self):
        Assignment.objects.create(cleaner=self.cleaner2, schedule=self.schedule, cleaning_day=self.cleaning_day1)
        self.assertFalse(self.schedule.create_assignment(self.cleaning_day1.date))

    def test__create_assignment__no_ratios(self):
        day = datetime.date(2010, 2, 15)
        no_group_schedule = Schedule.objects.create(name="no_group_schedule", cleaners_per_date=1, frequency=1)
        self.assertFalse(no_group_schedule.create_assignment(day))

    def test__create_assignment__no_eligible_cleaner(self):
        assignment = self.schedule.create_assignment(self.cleaning_day1.date)
        self.assertEqual(assignment.cleaner, self.schedule.deployment_ratios(self.cleaning_day1.date)[0][0])

    def test__create_assignment__all_cleaners_excluded(self):
        self.cleaning_day1.excluded.add(self.cleaner1, self.cleaner2)
        assignment = self.schedule.create_assignment(self.cleaning_day1.date)
        self.assertEqual(assignment.cleaner, self.schedule.deployment_ratios(self.cleaning_day1.date)[0][0])

    def test__create_assignment__eligible_cleaners(self):
        assignment = self.schedule.create_assignment(self.cleaning_day2.date)
        self.assertEqual(assignment.cleaner, self.cleaner1)
        self.assertEqual(assignment.cleaning_day, self.cleaning_day2)

    def test__save__cleaners_per_date__changes(self):
        self.schedule.cleaners_per_date = 10
        with self.assertRaises(OperationalError):
            self.schedule.save()

    def test__save__frequency__changes(self):
        self.schedule.frequency = 10
        with self.assertRaises(OperationalError):
            self.schedule.save()
