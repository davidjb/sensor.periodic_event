import datetime

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_ICON, CONF_WEEKDAY, ATTR_DATE
import homeassistant.util.dt as dt_util
from homeassistant.helpers.event import async_track_point_in_utc_time
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity


CONF_EPOCH = 'epoch'
CONF_FREQUENCY = 'frequency'

DATE_STR_FORMAT = '%A, %Y-%m-%d'
WEEKDAY_STR_FORMAT = '%A'

DEFAULT_NAME = 'Upcoming Event'
DEFAULT_ICON = 'mdi:calendar-clock'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_EPOCH): cv.date,
    vol.Optional(CONF_ICON): cv.icon,
    vol.Required(CONF_FREQUENCY): vol.Coerce(int),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Setup the sensor platform."""
    sensor_name = config.get(CONF_NAME)
    icon = config.get(CONF_ICON)
    epoch = config.get(CONF_EPOCH)
    frequency = config.get(CONF_FREQUENCY)

    sensors = [
        PeriodicEventSensor(hass, f'{sensor_name} Date', icon, epoch,
                            frequency),
        PeriodicEventRelativeSensor(hass, sensor_name, icon, epoch, frequency),
    ]

    for sensor in sensors:
        async_track_point_in_utc_time(
            hass, sensor.point_in_time_listener, sensor.get_next_interval())

    async_add_entities(sensors, True)


class PeriodicEventSensor(Entity):

    def __init__(self, hass, name, icon, epoch, frequency):
        """Initialize the sensor."""
        self.hass = hass

        self._name = name
        self._icon = icon
        self._epoch = epoch
        self._frequency = frequency

        self._state = None
        self._next_event = None

        self._update_internal_state(dt_util.utcnow())

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        return {
            ATTR_DATE: self._next_event.isoformat(),
            CONF_WEEKDAY: self._next_event.strftime(WEEKDAY_STR_FORMAT)
        }

    def _get_next_event(self, now):
        """ Compute the next event """
        from dateutil import relativedelta
        today = dt_util.as_local(now).date()
        weekday = relativedelta.weekdays[self._epoch.weekday()]

        next_event = today + relativedelta.relativedelta(weekday=weekday)

        # Check if this date matches the frequency after epoch, or else
        # calculate the correct date
        remainder = (next_event - self._epoch).days / 7 % self._frequency
        if remainder != 0:
            next_event = next_event + \
                datetime.timedelta(weeks=self._frequency - remainder)
        return next_event

    def get_next_interval(self, now=None):
        """Compute next time update should occur (at next event)."""
        if not now:
            now = dt_util.utcnow()

        next_event = self._get_next_event(now)

        return datetime.datetime(
            next_event.year, next_event.month, next_event.day)

    def _update_internal_state(self, now):
        self._next_event = self._get_next_event(now)
        self._state = self._next_event.strftime(DATE_STR_FORMAT)

    @callback
    def point_in_time_listener(self, now):
        """Update state and schedule same listener to run again."""
        self._update_internal_state(now)
        self.async_schedule_update_ha_state()
        async_track_point_in_utc_time(
            self.hass, self.point_in_time_listener, self.get_next_interval())


class PeriodicEventRelativeSensor(PeriodicEventSensor):

    def get_next_interval(self, now=None):
        """Compute next time update should occur (eg updates daily)."""
        if now is None:
            now = dt_util.utcnow()
        start_of_day = dt_util.start_of_local_day(dt_util.as_local(now))
        return start_of_day + datetime.timedelta(days=1)

    def _update_internal_state(self, now):
        from natural.date import duration

        super()._update_internal_state(now)

        # Compute the human-readable text between today and the next event
        today = dt_util.as_local(now).date()
        difference = self._next_event - today
        if (difference.days == 0):
            self._state = 'Today'
        elif (difference.days == 1):
            self._state = 'Tomorrow'
        else:
            self._state = duration(self._next_event, now=today, precision=2)
