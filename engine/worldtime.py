"""Expanse's canonical calendar. A minute remains sixty seconds on its clock."""
HOURS_PER_DAY = 25
MINUTES_PER_DAY = 1500
DAYS_PER_WEEK = 9
DAYS_PER_MONTH = 26
MONTHS_PER_YEAR = 8
DAYS_PER_YEAR = 208
MINUTES_PER_YEAR = 312000
DAYS_PER_SEASON = 52
MINUTES_PER_SEASON = 78000
DAYLIGHT_MINUTES = 750
SEASONS = ('spring', 'summer', 'autumn', 'winter')


def date(minute, sunrise_minute=375):
    minute=max(0,int(minute));day,clock=divmod(minute,MINUTES_PER_DAY)
    year,year_day=divmod(day,DAYS_PER_YEAR);month,month_day=divmod(year_day,DAYS_PER_MONTH)
    return dict(year=year+1,month=month+1,day=month_day+1,day_of_year=year_day+1,
        absolute_day=day+1,weekday=day%DAYS_PER_WEEK+1,week=day//DAYS_PER_WEEK+1,
        hour=clock//60,minute=clock%60,sunrise_minute=sunrise_minute%MINUTES_PER_DAY,
        minutes_per_day=MINUTES_PER_DAY,daylight_minutes=DAYLIGHT_MINUTES,daylight=(clock-sunrise_minute)%MINUTES_PER_DAY<DAYLIGHT_MINUTES)


def season(minute, latitude=45):
    index=(int(minute)//MINUTES_PER_SEASON)%4
    if latitude<0:index=(index+2)%4
    return SEASONS[index]


def describe(minute, sunrise_minute=375):
    d=date(minute,sunrise_minute)
    return f'Year {d["year"]}, month {d["month"]}, day {d["day"]} | weekday {d["weekday"]}/9 | {d["hour"]:02d}:{d["minute"]:02d} | '+('daylight' if d['daylight'] else 'night')


def initial_minute(metadata):
    """Fresh-world clock only; existing state always takes precedence.

    An explicit Creator clock can deliberately start at night. Otherwise start
    at the authored dawn (06:15 under Expanse's default dawn).
    """
    start=metadata.get('start_minute')
    if type(start) is int and 0<=start<MINUTES_PER_DAY:return start
    dawn=metadata.get('sunrise_minute',375)
    if type(dawn) is not int or not 0<=dawn<MINUTES_PER_DAY:dawn=375
    return dawn
