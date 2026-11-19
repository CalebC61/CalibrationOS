import Shell from "../components/Shell";
import SectionSwitch from "../components/SectionSwitch";
import { useOwnerSection } from "../lib/ownerSections";
import ChargeQueue from "./ChargeQueue";
import Invoices from "./Invoices";

const MONEY_SECTIONS = ["charges", "invoices"];

export default function Money() {
  const [section, choose] = useOwnerSection("/money", MONEY_SECTIONS, "charges");
  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Money</h1>
      <SectionSwitch
        label="Money"
        value={section}
        onChange={choose}
        options={[
          { id: "charges", label: "Charges" },
          { id: "invoices", label: "Invoices" },
        ]}
      />
      {section === "invoices" ? <Invoices bare /> : <ChargeQueue bare />}
    </Shell>
  );
}
