# NHS COVID-19 Data

This repo contains tools to regularly update an SQLite database with data fetched from the API
of the [NHS COVID-19 App](https://covid19.nhs.uk/), and NHS testing availability.

**The collected data can be downloaded [here](https://files.russss.dev/nhs_covid19_app_data.db)**

This data powers the [app stats page on my Covid Tracker site](https://russss.github.io/covidtracker/app.html).

## Data Format

The database consists of the following tables:

### exposure_keys

This table contains the _metadata_ associated with the temporary exposure keys which have been
broadcast as infected. It does not contain the value of the keys themselves, which is of no
statistical use and may pose some limited potential risk in identification attacks.

The fields in the table match those in the [exposure key export format](https://developers.google.com/android/exposure-notifications/exposure-key-file-format), with the exception of the `export_date` field which is
the `end_timestamp` of the key export in which that key was seen.

### risky_venues

This contains the data from the [risky-venues endpoint](https://distribution-te-prod.prod.svc-test-trace.nhs.uk/distribution/risky-venues) which lists venue IDs where exposure could have taken place. This is used by the QR code checkin system.

**Data note:** Some "risky venue" data is missing between Aug 3-6 2021. 

### exposure_configuration

This table contains the exposure configuration JSON file fetched from [this endpoint](https://distribution-te-prod.prod.svc-test-trace.nhs.uk/distribution/exposure-configuration), with a new record inserted whenever this changes.

This file is also available in the [public git repository](https://github.com/nihp-public/covid19-app-system-public/blob/master/src/static/exposure-configuration.json), however this is a mirror and may not be updated immediately when the configuration changes.

For changes dated before 2021-07-11, the data in the table has been backfilled using data from the git repository, and so the timestamp will be approximate.

### walk_in_pcr_availability

Start date: 2021-12-27

Walk-in PCR test availability across the UK, in the JSON format returned by the website. This table
is only updated when the JSON data substantively changes.

### home_test_availability

Start date: 2021-12-27

Home test ordering availability, for PCR and LFD tests.
