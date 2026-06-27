-- Migration 025 — correct cpd_incidents.type (violent / property / other)
--
-- The original silver load classified crime by the IUCR 2-char PREFIX, which is
-- wrong: prefix 08 is THEFT (property) and prefix 05 is aggravated ASSAULT
-- (violent). That dropped ~21% of all crime (theft) to 'other' and filed
-- aggravated assault as 'property' — corrupting any violent/property metric
-- (gold_address_intel.violent_5yr/property_5yr, safety_at_point()).
--
-- Correct classification = FBI Part 1 (index) crimes only, from the official
-- Chicago IUCR dictionary (data.cityofchicago.org/resource/c7ck-438e,
-- index_code = 'I') grouped by primary_description. Same code lists as
-- scripts/transformers/cpd.classify_iucr (which fixes it for future loads).
--
-- Run server-side (a single set-based UPDATE); a REST/PostgREST bulk update of
-- this 1.47M-row table times out because iucr is unindexed.

UPDATE cpd_incidents
SET type = CASE
  WHEN iucr IN (
    '0110','0130',
    '0261','0262','0263','0264','0265','0266','0271','0272','0273','0274','0275','0281','0291',
    '0312','0313','031A','031B','0320','0325','0326','0330','0331','0334','0337','033A','033B','0340',
    '041A','041B','0420','0430','0450','0451','0452','0453','0461','0462','0479','0480','0481','0482',
    '0483','0485','0487','0488','0489','0495','0496','0497','0498','0499',
    '051A','051B','0520','0530','0550','0551','0552','0553','0555','0556','0557','0558'
  ) THEN 'violent'
  WHEN iucr IN (
    '0610','0620','0630','0650','0710','0760',
    '0810','0820','0830','0840','0841','0842','0843','0850','0860','0865','0870','0880','0890','0895',
    '0910','0915','0917','0918','0920','0925','0927','0928','0930','0935','0937','0938',
    '1010','1020','1025','1090'
  ) THEN 'property'
  ELSE 'other'
END
WHERE type IS DISTINCT FROM (CASE
  WHEN iucr IN (
    '0110','0130',
    '0261','0262','0263','0264','0265','0266','0271','0272','0273','0274','0275','0281','0291',
    '0312','0313','031A','031B','0320','0325','0326','0330','0331','0334','0337','033A','033B','0340',
    '041A','041B','0420','0430','0450','0451','0452','0453','0461','0462','0479','0480','0481','0482',
    '0483','0485','0487','0488','0489','0495','0496','0497','0498','0499',
    '051A','051B','0520','0530','0550','0551','0552','0553','0555','0556','0557','0558'
  ) THEN 'violent'
  WHEN iucr IN (
    '0610','0620','0630','0650','0710','0760',
    '0810','0820','0830','0840','0841','0842','0843','0850','0860','0865','0870','0880','0890','0895',
    '0910','0915','0917','0918','0920','0925','0927','0928','0930','0935','0937','0938',
    '1010','1020','1025','1090'
  ) THEN 'property'
  ELSE 'other'
END);

-- After this, refresh the gold layer so violent/property counts pick it up:
--   SELECT refresh_gold_layer();
