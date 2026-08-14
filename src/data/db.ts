import getDatabase, { Database } from ".";

const db = getDatabase(Database.WDFP_DATA)

export function getDb() { return db; }
