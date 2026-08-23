"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

interface AccountOption {
  id: string;
  name: string;
  role: string;
}

const ACCOUNTS: AccountOption[] = [
  { id: "ACCT-001", name: "Northstar Logistics", role: "staff" },
  { id: "ACCT-002", name: "LumenWorks", role: "staff" },
];

interface AccountSwitcherProps {
  account: AccountOption;
  onChange: (account: AccountOption) => void;
}

export function AccountSwitcher({ account, onChange }: AccountSwitcherProps) {
  return (
    <div className="flex items-center gap-2">
      <Badge variant="outline" className="text-xs text-gray-400 border-gray-600">
        {account.role === "staff" ? "🛡 Staff" : "👤 Customer"}
      </Badge>
      <Select
        value={account.id}
        onValueChange={(val) => {
          const found = ACCOUNTS.find((a) => a.id === val);
          if (found) onChange(found);
        }}
      >
        <SelectTrigger className="w-48 h-8 bg-gray-800 border-gray-700 text-gray-200 text-xs focus:ring-indigo-500">
          <SelectValue placeholder="Select account" />
        </SelectTrigger>
        <SelectContent className="bg-gray-800 border-gray-700">
          {ACCOUNTS.map((a) => (
            <SelectItem key={a.id} value={a.id} className="text-gray-200 text-xs focus:bg-gray-700">
              <div>
                <p className="font-medium">{a.name}</p>
                <p className="text-gray-500">{a.id}</p>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
