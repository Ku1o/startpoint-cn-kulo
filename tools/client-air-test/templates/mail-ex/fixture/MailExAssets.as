package fixture {
import pinball.asset.logic.ILogicAssetContainer;
import pinball.master.runtime.MasterTable;
import pinball.master.generated.ExBoostItemAcquisitionTable;
import pinball.master.generated.ExBoostItemAcquisitionValues;
public class MailExAssets implements ILogicAssetContainer {
public static var characterRows:Object;
public var table:ExBoostItemAcquisitionTable=new ExBoostItemAcquisitionTable();
public function MailExAssets(master:Object){characterRows=master.characters;var rows:MailExMasterMap=new MailExMasterMap();for each(var row:Object in master.acquisitionRows){var inner:MailExMasterMap;if(!rows.exists(row.rarity)){inner=new MailExMasterMap();rows.put(row.rarity,inner);}else inner=rows.get(row.rarity) as MailExMasterMap;inner.put(row.element,new ExBoostItemAcquisitionValues([String(row.item_id),String(row.item_count)]));}table.data=rows;}
public function getMasterTable(c:Class):MasterTable{if(c!==ExBoostItemAcquisitionTable)throw new Error("Unsupported external master table "+c);return table;}
}}
