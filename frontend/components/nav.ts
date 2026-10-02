import {
  LayoutDashboard, Wallet, Search, ArrowLeftRight, Brain, Coins, PieChart,
  Bell, Trophy, Network, Sparkles, Settings, type LucideIcon,
} from "lucide-react";

export const NAV: { label: string; href: string; icon: LucideIcon }[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Whale Wallets", href: "/wallets", icon: Wallet },
  { label: "Wallet Explorer", href: "/explorer", icon: Search },
  { label: "Transactions", href: "/transactions", icon: ArrowLeftRight },
  { label: "Smart Money", href: "/smart-money", icon: Brain },
  { label: "Token Analytics", href: "/tokens", icon: Coins },
  { label: "Portfolio Analytics", href: "/portfolio", icon: PieChart },
  { label: "Whale Alerts", href: "/alerts", icon: Bell },
  { label: "Wallet Leaderboard", href: "/leaderboard", icon: Trophy },
  { label: "Network Explorer", href: "/networks", icon: Network },
  { label: "AI Insights", href: "/ai", icon: Sparkles },
  { label: "Settings", href: "/settings", icon: Settings },
];
