import React from 'react';
import './globals.css';

export const metadata = {
  title: 'Stocker - Multi-Vendor Options Core',
  description: 'Live Multi-Vendor Options Monitoring and Automated Execution Engine',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
