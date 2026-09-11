import sqlite3
conn = sqlite3.connect('comm_log.db')

# Check: does any campaign have parent_id = 9101?
print('=== Campaigns with parent_id=9101 ===')
print(conn.execute('SELECT * FROM campaign WHERE parent_id=9101').fetchall())

# Check: does 9101 have a parent?
print('=== Campaign 9101 ===')
print(conn.execute('SELECT id, parent_id, name FROM campaign WHERE id=9101').fetchall())

# All rows for 9101
print('=== Comm log rows for campaign 9101 ===')
for r in conn.execute('SELECT id, customer_id, delivery_status, sent_time FROM communication_log WHERE communication_id=9101 ORDER BY sent_time'):
    print(r)

# Standalone = every send is its own event
print()
rows_9101 = conn.execute('SELECT COUNT(*) FROM communication_log WHERE communication_id=9101').fetchone()[0]
dist_9101 = conn.execute('SELECT COUNT(DISTINCT customer_id) FROM communication_log WHERE communication_id=9101').fetchone()[0]
print('COUNT(*) for 9101 sends:', rows_9101)
print('COUNT(DISTINCT customer_id) for 9101:', dist_9101)

# Re-read README line 74-75:
# "A campaign with no retry chain at all (no other campaign points at it,
#  and it points at nothing) is a standalone communication - every send
#  under it is its own event, whether or not the same customer appears twice."
# -> 9101 is standalone -> use COUNT(*) not COUNT(DISTINCT customer_id)
# So 9101 contributes 7, not 6

print()
print('Family A  (9001->9002->9003) = 10 distinct customers')
print('9101 standalone               = 7 sends (C20 x2 + C21-C25)')
print('Family B  (9201->9202)        = 5 distinct customers')
print('TARGET_BASE = 10 + 7 + 5 =', 10 + rows_9101 + 5)

# Also verify: 9201 and 9202 - does 9201 have parent? does anything point to 9201?
print()
print('=== Campaign 9201 structure ===')
print(conn.execute('SELECT id, parent_id, name FROM campaign WHERE id IN (9201, 9202)').fetchall())
# 9201 has no parent and 9202 points to it -> 9201 IS a chain root (not standalone)
# So 9201+9202 family uses distinct customer logic

conn.close()
