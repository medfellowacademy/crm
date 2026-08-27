import React, { useState, useMemo } from 'react';
import * as XLSX from 'xlsx';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Select,
  DatePicker,
  Space,
  Tooltip,
  Avatar,
  Progress,
  Typography,
  Tabs,
  Empty,
  Badge,
  Button,
  Input,
  Drawer
} from 'antd';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter
} from 'recharts';
import {
  ClockCircleOutlined,
  UserOutlined,
  GlobalOutlined,
  BookOutlined,
  FlagOutlined,
  RiseOutlined,
  FallOutlined,
  SearchOutlined,
  ReloadOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  TeamOutlined,
  TrophyOutlined,
  WarningOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';
import { leadsAPI, usersAPI, coursesAPI } from '../api/api';

dayjs.extend(duration);
dayjs.extend(relativeTime);

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;

const LeadAnalysisPage = () => {
  const [selectedCountry, setSelectedCountry] = useState('all');
  const [selectedCourse, setSelectedCourse] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [selectedUser, setSelectedUser] = useState('all');
  const [dateRange, setDateRange] = useState([dayjs().subtract(90, 'days'), dayjs()]);
  const [searchText, setSearchText] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [drawer, setDrawer] = useState({ open: false, title: '', leads: [] });

  const openDrawer = (title, leadsSubset) => setDrawer({ open: true, title, leads: leadsSubset });

  // Fetch data
  const { data: leadsData, isLoading: leadsLoading, refetch: refetchLeads } = useQuery({
    queryKey: ['leads'],
    queryFn: () => leadsAPI.getAll({ limit: 10000 }).then(res => res.data)
  });

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersAPI.getAll().then(res => res.data)
  });

  const { data: coursesData, isLoading: coursesLoading } = useQuery({
    queryKey: ['courses'],
    queryFn: () => coursesAPI.getAll().then(res => res.data)
  });

  const leads = leadsData?.leads || [];
  const users = Array.isArray(usersData) ? usersData : (usersData?.users || []);
  const courses = Array.isArray(coursesData) ? coursesData : (coursesData?.courses || []);

  // Calculate lead age in days
  const calculateLeadAge = (createdAt) => {
    if (!createdAt) return 0;
    return dayjs().diff(dayjs(createdAt), 'days');
  };

  // Calculate days since last update
  const calculateDaysSinceUpdate = (updatedAt) => {
    if (!updatedAt) return 0;
    return dayjs().diff(dayjs(updatedAt), 'days');
  };

  // Filter leads — inclusive boundary dates, course derived from actual lead data
  const filteredLeads = useMemo(() => {
    if (!leads || !dateRange || !dateRange[0] || !dateRange[1]) return [];
    const from = dateRange[0].startOf('day');
    const to   = dateRange[1].endOf('day');

    return leads.filter(lead => {
      const leadDate = dayjs(lead.created_at);
      const matchesDate    = !leadDate.isBefore(from) && !leadDate.isAfter(to);
      const matchesCountry = selectedCountry === 'all' || lead.country === selectedCountry;
      const matchesCourse  = selectedCourse  === 'all' || lead.course_interested === selectedCourse;
      const matchesStatus  = selectedStatus  === 'all' || lead.status === selectedStatus;
      const matchesUser    = selectedUser    === 'all' || lead.assigned_to === selectedUser;
      const matchesSearch  = !searchText ||
        lead.full_name?.toLowerCase().includes(searchText.toLowerCase()) ||
        lead.email?.toLowerCase().includes(searchText.toLowerCase()) ||
        lead.phone?.includes(searchText);

      return matchesDate && matchesCountry && matchesCourse && matchesStatus && matchesUser && matchesSearch;
    });
  }, [leads, dateRange, selectedCountry, selectedCourse, selectedStatus, selectedUser, searchText]);

  // Get unique filter values derived from actual lead data (not from separate API calls)
  const countries     = useMemo(() => [...new Set(leads.map(l => l.country).filter(Boolean))].sort(), [leads]);
  const statuses      = useMemo(() => [...new Set(leads.map(l => l.status).filter(Boolean))].sort(), [leads]);
  const courseOptions = useMemo(() => [...new Set(leads.map(l => l.course_interested).filter(Boolean))].sort(), [leads]);

  // CSV export of filteredLeads
  const handleExport = () => {
    const headers = ['Name', 'Status', 'Source', 'Country', 'Course', 'Phone', 'Email', 'Assigned To', 'Created At'];
    const rows = filteredLeads.map(l => [
      l.full_name || '',
      l.status || '',
      l.source || '',
      l.country || '',
      l.course_interested || '',
      l.phone || '',
      l.email || '',
      l.assigned_to || '',
      l.created_at ? new Date(l.created_at).toLocaleDateString('en-IN') : '',
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `lead-analysis-${dateRange[0].format('YYYY-MM-DD')}-to-${dateRange[1].format('YYYY-MM-DD')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── PDF report: generates self-contained HTML + opens print dialog ────────
  const handleDownloadPDF = () => {
    const fromLabel = dateRange[0].format('DD MMM YYYY');
    const toLabel   = dateRange[1].format('DD MMM YYYY');
    const now       = dayjs().format('DD MMM YYYY, h:mm A');

    // SVG helpers
    const hBar = (items, nameKey, valueKey, color) => {
      const max   = Math.max(...items.map(d => d[valueKey]), 1);
      const rowH  = 22;
      const labelW = 170;
      const barAreaW = 280;
      const svgH  = items.length * rowH + 16;
      const rows  = items.map((d, i) => {
        const bw = Math.round((d[valueKey] / max) * barAreaW);
        const y  = i * rowH + 8;
        const label = String(d[nameKey] || '').length > 24
          ? String(d[nameKey]).slice(0, 23) + '…' : String(d[nameKey] || '');
        return `<text x="${labelW - 6}" y="${y + 14}" text-anchor="end" font-size="11" fill="#374151" font-family="sans-serif">${label}</text>
                <rect x="${labelW}" y="${y + 2}" width="${Math.max(bw, 2)}" height="15" fill="${color}" rx="3"/>
                <text x="${labelW + bw + 5}" y="${y + 14}" font-size="11" fill="#374151" font-family="sans-serif">${d[valueKey]}</text>`;
      }).join('');
      return `<svg width="${labelW + barAreaW + 60}" height="${svgH}" xmlns="http://www.w3.org/2000/svg">${rows}</svg>`;
    };

    const vBar = (items, nameKey, valueKey, color) => {
      const max    = Math.max(...items.map(d => d[valueKey]), 1);
      const barW   = 56;
      const gap    = 12;
      const chartH = 150;
      const totalW = items.length * (barW + gap) + 20;
      const totalH = chartH + 52;
      const bars = items.map((d, i) => {
        const bh  = Math.round((d[valueKey] / max) * chartH);
        const x   = i * (barW + gap) + 10;
        const y   = chartH - bh + 10;
        const lbl = String(d[nameKey] || '').replace(' days', 'd');
        return `<rect x="${x}" y="${y}" width="${barW}" height="${bh}" fill="${color}" rx="4"/>
                <text x="${x + barW / 2}" y="${y - 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#374151" font-family="sans-serif">${d[valueKey]}</text>
                <text x="${x + barW / 2}" y="${chartH + 26}" text-anchor="middle" font-size="10" fill="#374151" font-family="sans-serif">${lbl}</text>`;
      }).join('');
      return `<svg width="${totalW}" height="${totalH}" xmlns="http://www.w3.org/2000/svg">${bars}</svg>`;
    };

    // Full distributions
    const allCountryPdf = Object.entries(
      filteredLeads.reduce((acc, l) => { if (l.country) acc[l.country] = (acc[l.country] || 0) + 1; return acc; }, {})
    ).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name, value }));

    const allCoursePdf = Object.entries(
      filteredLeads.reduce((acc, l) => { if (l.course_interested) acc[l.course_interested] = (acc[l.course_interested] || 0) + 1; return acc; }, {})
    ).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name, value }));

    const totalLeads_  = filteredLeads.length;
    const enrolled_    = filteredLeads.filter(l => l.status === 'Enrolled').length;
    const active_      = filteredLeads.filter(l => ['Fresh','Follow Up','Warm','Hot','Re-assigned Lead'].includes(l.status)).length;
    const stale_       = filteredLeads.filter(l => calculateDaysSinceUpdate(l.updated_at) > 7).length;
    const lost_        = filteredLeads.filter(l => ['Not Interested','Not Answering','Junk','Dropped','TMT No Response','Test Lead'].includes(l.status)).length;
    const revenue_     = filteredLeads.reduce((s, l) => s + (l.potential_revenue || 0), 0);
    const convRate_    = totalLeads_ > 0 ? ((enrolled_ / totalLeads_) * 100).toFixed(1) : '0.0';

    const sColor = { 'Fresh':'#13c2c2','Follow Up':'#1890ff','Warm':'#fa8c16','Hot':'#f5222d',
                     'Enrolled':'#52c41a','Not Interested':'#8c8c8c','Not Answering':'#78716c','Junk':'#9ca3af',
                     'Will Enroll Later':'#13a8a8','Dropped':'#c41d7f','TMT No Response':'#faad14',
                     'Re-assigned Lead':'#2f54eb','Test Lead':'#9ca3af' };

    const statCard = (lbl, val, clr) =>
      `<div style="flex:1;min-width:110px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px">
         <div style="font-size:11px;color:#64748b;margin-bottom:3px">${lbl}</div>
         <div style="font-size:20px;font-weight:700;color:${clr}">${val}</div>
       </div>`;

    const statusRows = [...statusDistribution].sort((a,b) => b.value - a.value).map(s =>
      `<tr>
         <td style="padding:5px 10px"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${sColor[s.name]||'#888'};margin-right:6px;vertical-align:middle"></span>${s.name}</td>
         <td style="padding:5px 10px;text-align:right;font-weight:600">${s.value}</td>
         <td style="padding:5px 10px;text-align:right;color:#64748b">${totalLeads_ > 0 ? ((s.value/totalLeads_)*100).toFixed(1) : 0}%</td>
       </tr>`
    ).join('');

    const perfRows = userPerformance.map((r, i) =>
      `<tr style="background:${i%2?'#f8fafc':'#fff'}">
         <td style="padding:4px 7px;text-align:center">${i+1}</td>
         <td style="padding:4px 7px;font-weight:600">${r.userName}</td>
         <td style="padding:4px 7px;text-align:center;font-weight:700">${r.totalLeads}</td>
         <td style="padding:4px 7px;text-align:center">${r.fresh}</td>
         <td style="padding:4px 7px;text-align:center">${r.followUp}</td>
         <td style="padding:4px 7px;text-align:center">${r.warm}</td>
         <td style="padding:4px 7px;text-align:center">${r.hot}</td>
         <td style="padding:4px 7px;text-align:center;color:#16a34a;font-weight:600">${r.enrolled}</td>
         <td style="padding:4px 7px;text-align:center">${r.notInterested}</td>
         <td style="padding:4px 7px;text-align:center">${r.notAnswering}</td>
         <td style="padding:4px 7px;text-align:center">${r.junk}</td>
         <td style="padding:4px 7px;text-align:center;color:#dc2626">${r.staleLeads}</td>
         <td style="padding:4px 7px;text-align:center;font-weight:700;color:${parseFloat(r.conversionRate)>=30?'#16a34a':parseFloat(r.conversionRate)>=15?'#d97706':'#dc2626'}">${r.conversionRate}%</td>
         <td style="padding:4px 7px;text-align:right;color:#16a34a">₹${Number(r.totalRevenue||0).toLocaleString('en-IN')}</td>
       </tr>`
    ).join('');

    const leadRows = filteredLeads.map((l, i) => {
      const age  = calculateLeadAge(l.created_at);
      const upd  = calculateDaysSinceUpdate(l.updated_at);
      return `<tr style="background:${i%2?'#f8fafc':'#fff'}">
        <td style="padding:4px 7px;font-size:11px">${l.full_name||''}</td>
        <td style="padding:4px 7px"><span style="background:${sColor[l.status]||'#888'}22;color:${sColor[l.status]||'#555'};padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600">${l.status||''}</span></td>
        <td style="padding:4px 7px;font-size:11px">${l.source||''}</td>
        <td style="padding:4px 7px;font-size:11px">${l.country||''}</td>
        <td style="padding:4px 7px;font-size:10px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.course_interested||''}</td>
        <td style="padding:4px 7px;font-size:11px">${l.assigned_to||''}</td>
        <td style="padding:4px 7px;text-align:center;font-size:11px;color:${age>60?'#dc2626':age>30?'#d97706':'#16a34a'}">${age}d</td>
        <td style="padding:4px 7px;text-align:center;font-size:11px;color:${upd>7?'#dc2626':'#374151'}">${upd}d</td>
        <td style="padding:4px 7px;text-align:right;font-size:11px;color:#16a34a">₹${Number(l.potential_revenue||0).toLocaleString('en-IN')}</td>
      </tr>`;
    }).join('');

    const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Lead Analysis Report ${fromLabel} to ${toLabel}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#1e293b;background:#fff;font-size:13px}
.page{padding:28px 36px;max-width:1080px;margin:0 auto}
h1{font-size:22px;color:#1e1b4b;margin-bottom:3px}
h2{font-size:15px;font-weight:700;color:#1e1b4b;margin:28px 0 12px;padding-bottom:6px;border-bottom:2px solid #e2e8f0}
.meta{font-size:11px;color:#64748b;margin-bottom:22px}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:4px}
.chart-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px}
.chart-title{font-size:12px;font-weight:600;color:#1e293b;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:11px}
thead tr{background:#1e1b4b;color:#fff}
thead th{padding:7px 8px;text-align:left;font-weight:600;font-size:10px;white-space:nowrap}
tbody td{border-bottom:1px solid #f1f5f9;vertical-align:middle}
.no-break{page-break-inside:avoid}
@media print{
  body{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .no-break{page-break-inside:avoid}
  thead{display:table-header-group}
  h2{page-break-before:auto}
}
</style></head><body>
<div class="page">

<h1>Lead Analysis Report</h1>
<div class="meta">
  Date Range: <strong>${fromLabel} → ${toLabel}</strong> &nbsp;·&nbsp;
  Generated: ${now} &nbsp;·&nbsp; ${totalLeads_} leads
</div>

<h2>Summary</h2>
<div class="stats">
  ${statCard('Total Leads',   totalLeads_,  '#1890ff')}
  ${statCard('Active',        active_,      '#1890ff')}
  ${statCard('Enrolled',      enrolled_,    '#16a34a')}
  ${statCard('Conv. Rate',    convRate_+'%', parseFloat(convRate_)>=10?'#16a34a':'#dc2626')}
  ${statCard('Lost',          lost_,        '#6b7280')}
  ${statCard('Stale >7d',     stale_,       '#dc2626')}
  ${statCard('Revenue',       '₹'+Number(revenue_).toLocaleString('en-IN'), '#16a34a')}
</div>

<h2>Overview Charts</h2>
<div class="charts-grid">
  <div class="chart-box no-break">
    <div class="chart-title">Lead Age Distribution</div>
    ${vBar(ageDistribution, 'name', 'count', '#1890ff')}
  </div>
  <div class="chart-box no-break">
    <div class="chart-title">Status Distribution</div>
    <table>
      <thead><tr><th>Status</th><th style="text-align:right">Count</th><th style="text-align:right">%</th></tr></thead>
      <tbody>${statusRows}</tbody>
    </table>
  </div>
  <div class="chart-box no-break">
    <div class="chart-title">Country Distribution (${allCountryPdf.length} countries)</div>
    ${hBar(allCountryPdf, 'name', 'value', '#52c41a')}
  </div>
  <div class="chart-box no-break">
    <div class="chart-title">Course Distribution (${allCoursePdf.length} courses)</div>
    ${hBar(allCoursePdf, 'name', 'value', '#722ed1')}
  </div>
</div>

<h2>User Performance</h2>
<table>
  <thead><tr>
    <th>#</th><th>Counselor</th><th>Total</th><th>Fresh</th><th>Follow Up</th>
    <th>Warm</th><th>Hot</th><th>Enrolled</th><th>Not Int.</th><th>Not Ans.</th>
    <th>Junk</th><th>Stale</th><th>Conv%</th><th>Revenue</th>
  </tr></thead>
  <tbody>${perfRows}</tbody>
</table>

<h2>Detailed Leads (${filteredLeads.length})</h2>
<table>
  <thead><tr>
    <th>Name</th><th>Status</th><th>Source</th><th>Country</th><th>Course</th>
    <th>Assigned To</th><th>Age</th><th>Last Upd.</th><th>Revenue</th>
  </tr></thead>
  <tbody>${leadRows}</tbody>
</table>

</div>
<script>window.addEventListener('load',function(){window.print();})</script>
</body></html>`;

    const w = window.open('', '_blank');
    if (!w) { alert('Please allow pop-ups for this site to download the PDF report.'); return; }
    w.document.write(html);
    w.document.close();
  };

  // Full Excel report — all chart data + user performance + detailed leads
  const handleDownloadReport = () => {
    const wb = XLSX.utils.book_new();

    const fromLabel = dateRange[0].format('DD MMM YYYY');
    const toLabel   = dateRange[1].format('DD MMM YYYY');

    // ── Sheet 1: Summary ────────────────────────────────────────────────────
    const totalLeads   = filteredLeads.length;
    const enrolled     = filteredLeads.filter(l => l.status === 'Enrolled').length;
    const active       = filteredLeads.filter(l => ['Fresh','Follow Up','Warm','Hot','Re-assigned Lead'].includes(l.status)).length;
    const stale        = filteredLeads.filter(l => calculateDaysSinceUpdate(l.updated_at) > 7).length;
    const lost         = filteredLeads.filter(l => ['Not Interested','Not Answering','Junk','Dropped','TMT No Response','Test Lead'].includes(l.status)).length;
    const totalRevenue = filteredLeads.reduce((s, l) => s + (l.potential_revenue || 0), 0);
    const convRate     = totalLeads > 0 ? ((enrolled / totalLeads) * 100).toFixed(1) : '0.0';
    const avgAge       = totalLeads > 0
      ? (filteredLeads.reduce((s, l) => s + calculateLeadAge(l.created_at), 0) / totalLeads).toFixed(1)
      : '0';
    const avgUpdate    = totalLeads > 0
      ? (filteredLeads.reduce((s, l) => s + calculateDaysSinceUpdate(l.updated_at), 0) / totalLeads).toFixed(1)
      : '0';

    const summarySheet = XLSX.utils.aoa_to_sheet([
      ['Lead Analysis Report'],
      [`Generated: ${dayjs().format('DD MMM YYYY, h:mm A')}`],
      [`Date Range: ${fromLabel} → ${toLabel}`],
      [],
      ['Metric', 'Value'],
      ['Total Leads', totalLeads],
      ['Active Leads (Fresh / Follow Up / Warm / Hot)', active],
      ['Enrolled', enrolled],
      ['Conversion Rate', `${convRate}%`],
      ['Lost Leads (Not Interested / Not Answering / Junk)', lost],
      ['Stale Leads (not updated >7 days)', stale],
      ['Stale Rate', `${totalLeads > 0 ? ((stale / totalLeads) * 100).toFixed(1) : 0}%`],
      ['Avg Lead Age', `${avgAge} days`],
      ['Avg Days Since Last Update', `${avgUpdate} days`],
      ['Total Revenue (₹)', totalRevenue],
    ]);
    summarySheet['!cols'] = [{ wch: 45 }, { wch: 20 }];
    XLSX.utils.book_append_sheet(wb, summarySheet, 'Summary');

    // ── Sheet 2: Age Distribution ────────────────────────────────────────────
    XLSX.utils.book_append_sheet(wb,
      XLSX.utils.aoa_to_sheet([
        ['Age Range', 'Lead Count'],
        ...ageDistribution.map(r => [r.name, r.count]),
      ]),
      'Age Distribution'
    );

    // ── Sheet 3: Status Distribution ────────────────────────────────────────
    XLSX.utils.book_append_sheet(wb,
      XLSX.utils.aoa_to_sheet([
        ['Status', 'Count'],
        ...statusDistribution.sort((a, b) => b.value - a.value).map(r => [r.name, r.value]),
      ]),
      'Status Distribution'
    );

    // ── Sheet 4: Country Distribution (all countries) ───────────────────────
    const allCountryDist = Object.entries(
      filteredLeads.reduce((acc, l) => { if (l.country) acc[l.country] = (acc[l.country] || 0) + 1; return acc; }, {})
    ).sort((a, b) => b[1] - a[1]);
    XLSX.utils.book_append_sheet(wb,
      XLSX.utils.aoa_to_sheet([
        ['Country', 'Leads'],
        ...allCountryDist.map(([name, value]) => [name, value]),
      ]),
      'Country Distribution'
    );

    // ── Sheet 5: Course Distribution (all courses) ───────────────────────────
    const allCourseDist = Object.entries(
      filteredLeads.reduce((acc, l) => { if (l.course_interested) acc[l.course_interested] = (acc[l.course_interested] || 0) + 1; return acc; }, {})
    ).sort((a, b) => b[1] - a[1]);
    XLSX.utils.book_append_sheet(wb,
      XLSX.utils.aoa_to_sheet([
        ['Course', 'Leads'],
        ...allCourseDist.map(([name, value]) => [name, value]),
      ]),
      'Course Distribution'
    );

    // ── Sheet 6: User Performance ────────────────────────────────────────────
    const perfHeaders = [
      '#', 'Counselor', 'Role', 'Total',
      'Fresh', 'Follow Up', 'Warm', 'Hot', 'Enrolled',
      'Not Interested', 'Not Answering', 'Junk', 'Other',
      'Stale >7d', 'Conv %', 'Avg Age (days)', 'Avg Days Since Update', 'Revenue (₹)',
    ];
    const perfRows = userPerformance.map((r, i) => [
      i + 1, r.userName, r.userRole, r.totalLeads,
      r.fresh, r.followUp, r.warm, r.hot, r.enrolled,
      r.notInterested, r.notAnswering, r.junk, r.other,
      r.staleLeads, `${r.conversionRate}%`, r.avgAge, r.avgDaysSinceUpdate, r.totalRevenue,
    ]);
    const perfSheet = XLSX.utils.aoa_to_sheet([perfHeaders, ...perfRows]);
    perfSheet['!cols'] = [
      { wch: 5 }, { wch: 22 }, { wch: 14 }, { wch: 8 },
      { wch: 8 }, { wch: 10 }, { wch: 8 }, { wch: 7 }, { wch: 9 },
      { wch: 14 }, { wch: 14 }, { wch: 7 }, { wch: 7 },
      { wch: 10 }, { wch: 8 }, { wch: 16 }, { wch: 20 }, { wch: 14 },
    ];
    XLSX.utils.book_append_sheet(wb, perfSheet, 'User Performance');

    // ── Sheet 7: Detailed Leads ──────────────────────────────────────────────
    const leadHeaders = [
      'Name', 'Status', 'Source', 'Country', 'Course', 'Phone', 'Email',
      'Assigned To', 'Lead Age (days)', 'Days Since Update', 'Revenue (₹)', 'Created At', 'Updated At',
    ];
    const leadRows = filteredLeads.map(l => [
      l.full_name     || '',
      l.status        || '',
      l.source        || '',
      l.country       || '',
      l.course_interested || '',
      l.phone         || '',
      l.email         || '',
      l.assigned_to   || '',
      calculateLeadAge(l.created_at),
      calculateDaysSinceUpdate(l.updated_at),
      l.potential_revenue || 0,
      l.created_at ? dayjs(l.created_at).format('DD MMM YYYY') : '',
      l.updated_at ? dayjs(l.updated_at).format('DD MMM YYYY') : '',
    ]);
    const leadSheet = XLSX.utils.aoa_to_sheet([leadHeaders, ...leadRows]);
    leadSheet['!cols'] = [
      { wch: 22 }, { wch: 14 }, { wch: 14 }, { wch: 12 }, { wch: 30 },
      { wch: 14 }, { wch: 28 }, { wch: 22 },
      { wch: 15 }, { wch: 17 }, { wch: 13 }, { wch: 14 }, { wch: 14 },
    ];
    XLSX.utils.book_append_sheet(wb, leadSheet, 'Detailed Leads');

    // ── Write file ───────────────────────────────────────────────────────────
    XLSX.writeFile(wb, `lead-analysis-report_${dateRange[0].format('YYYY-MM-DD')}_to_${dateRange[1].format('YYYY-MM-DD')}.xlsx`);
  };

  // Calculate metrics
  const metrics = useMemo(() => {
    if (!filteredLeads.length) return {};

    const totalLeads = filteredLeads.length;
    const avgAge = filteredLeads.reduce((sum, lead) => sum + calculateLeadAge(lead.created_at), 0) / totalLeads;
    const avgDaysSinceUpdate = filteredLeads.reduce((sum, lead) => sum + calculateDaysSinceUpdate(lead.updated_at), 0) / totalLeads;
    
    const staleLeads = filteredLeads.filter(l => calculateDaysSinceUpdate(l.updated_at) > 7).length;
    const freshLeads = filteredLeads.filter(l => calculateDaysSinceUpdate(l.updated_at) <= 2).length;
    const activeLeads = filteredLeads.filter(l => ['Fresh', 'Follow Up', 'Warm', 'Hot'].includes(l.status)).length;
    const convertedLeads = filteredLeads.filter(l => l.status === 'Enrolled').length;
    const lostLeads = filteredLeads.filter(l => ['Not Interested', 'Not Answering', 'Junk', 'Dropped', 'TMT No Response', 'Test Lead'].includes(l.status)).length;

    const conversionRate = totalLeads > 0 ? (convertedLeads / totalLeads) * 100 : 0;
    const lostRate = totalLeads > 0 ? (lostLeads / totalLeads) * 100 : 0;
    const staleRate = totalLeads > 0 ? (staleLeads / totalLeads) * 100 : 0;

    return {
      totalLeads,
      avgAge: avgAge.toFixed(1),
      avgDaysSinceUpdate: avgDaysSinceUpdate.toFixed(1),
      staleLeads,
      freshLeads,
      activeLeads,
      convertedLeads,
      lostLeads,
      conversionRate: conversionRate.toFixed(1),
      lostRate: lostRate.toFixed(1),
      staleRate: staleRate.toFixed(1)
    };
  }, [filteredLeads]);

  // Lead age distribution
  const ageDistribution = useMemo(() => {
    const ranges = [
      { name: '0-7 days', min: 0, max: 7, count: 0 },
      { name: '8-14 days', min: 8, max: 14, count: 0 },
      { name: '15-30 days', min: 15, max: 30, count: 0 },
      { name: '31-60 days', min: 31, max: 60, count: 0 },
      { name: '60+ days', min: 61, max: 999999, count: 0 }
    ];

    filteredLeads.forEach(lead => {
      const age = calculateLeadAge(lead.created_at);
      const range = ranges.find(r => age >= r.min && age <= r.max);
      if (range) range.count++;
    });

    return ranges;
  }, [filteredLeads]);

  // Status distribution
  const statusDistribution = useMemo(() => {
    const distribution = {};
    filteredLeads.forEach(lead => {
      distribution[lead.status] = (distribution[lead.status] || 0) + 1;
    });
    return Object.entries(distribution).map(([name, value]) => ({ name, value }));
  }, [filteredLeads]);

  // Country distribution
  const countryDistribution = useMemo(() => {
    const distribution = {};
    filteredLeads.forEach(lead => {
      if (lead.country) {
        distribution[lead.country] = (distribution[lead.country] || 0) + 1;
      }
    });
    return Object.entries(distribution)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [filteredLeads]);

  // Course distribution
  const courseDistribution = useMemo(() => {
    const distribution = {};
    filteredLeads.forEach(lead => {
      if (lead.course_interested) {
        distribution[lead.course_interested] = (distribution[lead.course_interested] || 0) + 1;
      }
    });
    return Object.entries(distribution)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [filteredLeads]);

  // User performance — every status tracked individually so counts always tally
  const userPerformance = useMemo(() => {
    const performance = {};

    filteredLeads.forEach(lead => {
      if (!lead.assigned_to) return;

      if (!performance[lead.assigned_to]) {
        const user = users.find(u => u.full_name === lead.assigned_to);
        performance[lead.assigned_to] = {
          userId: lead.assigned_to,
          userName: user?.full_name || lead.assigned_to || 'Unknown',
          userRole: user?.role || 'Unknown',
          totalLeads: 0,
          fresh: 0, followUp: 0, warm: 0, hot: 0,
          enrolled: 0,
          notInterested: 0, notAnswering: 0, junk: 0,
          other: 0,
          staleLeads: 0,
          totalRevenue: 0,
          ages: [],
          updateDays: [],
        };
      }

      const p = performance[lead.assigned_to];
      p.totalLeads++;
      p.ages.push(calculateLeadAge(lead.created_at));
      p.updateDays.push(calculateDaysSinceUpdate(lead.updated_at));
      if (calculateDaysSinceUpdate(lead.updated_at) > 7) p.staleLeads++;

      const s = lead.status;
      if (s === 'Fresh')               p.fresh++;
      else if (s === 'Follow Up')      p.followUp++;
      else if (s === 'Warm')           p.warm++;
      else if (s === 'Hot')            p.hot++;
      else if (s === 'Enrolled')     { p.enrolled++; p.totalRevenue += lead.potential_revenue || 0; }
      else if (s === 'Not Interested') p.notInterested++;
      else if (s === 'Not Answering')  p.notAnswering++;
      else if (s === 'Junk')           p.junk++;
      else                             p.other++;
    });

    return Object.values(performance).map(p => ({
      ...p,
      activeLeads:    p.fresh + p.followUp + p.warm + p.hot,
      convertedLeads: p.enrolled,
      lostLeads:      p.notInterested + p.notAnswering + p.junk,
      avgAge: (p.ages.reduce((a, b) => a + b, 0) / (p.ages.length || 1)).toFixed(1),
      avgDaysSinceUpdate: (p.updateDays.reduce((a, b) => a + b, 0) / (p.updateDays.length || 1)).toFixed(1),
      conversionRate: p.totalLeads > 0 ? ((p.enrolled / p.totalLeads) * 100).toFixed(1) : '0.0',
      staleRate:      p.totalLeads > 0 ? ((p.staleLeads / p.totalLeads) * 100).toFixed(1) : '0.0',
    })).sort((a, b) => b.totalLeads - a.totalLeads);
  }, [filteredLeads, users]);

  // Lead aging scatter plot data
  const agingScatterData = useMemo(() => {
    return filteredLeads.map(lead => ({
      age: calculateLeadAge(lead.created_at),
      daysSinceUpdate: calculateDaysSinceUpdate(lead.updated_at),
      name: lead.full_name,
      status: lead.status,
      aiScore: lead.ai_score || 0
    }));
  }, [filteredLeads]);

  // Status colors
  const statusColors = {
    'Fresh': '#13c2c2',
    'Follow Up': '#1890ff',
    'Warm': '#fa8c16',
    'Hot': '#f5222d',
    'Enrolled': '#52c41a',
    'Not Interested': '#8c8c8c',
    'Not Answering': '#8c8c8c',
    'Junk': '#8c8c8c',
    'Will Enroll Later': '#13a8a8',
    'Dropped': '#c41d7f',
    'TMT No Response': '#faad14',
    'Re-assigned Lead': '#2f54eb',
    'Test Lead': '#8c8c8c',
  };

  // Chart colors
  const COLORS = ['#1890ff', '#52c41a', '#fa8c16', '#f5222d', '#722ed1', '#13c2c2', '#eb2f96', '#faad14'];

  // Table columns
  const columns = [
    {
      title: 'Lead Name',
      dataIndex: 'full_name',
      key: 'name',
      fixed: 'left',
      width: 180,
      render: (text, record) => (
        <Space>
          <Avatar style={{ backgroundColor: '#1890ff' }}>
            {text?.charAt(0)?.toUpperCase()}
          </Avatar>
          <div>
            <div style={{ fontWeight: 500 }}>{text}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Score: {record.ai_score || 'N/A'}
            </Text>
          </div>
        </Space>
      )
    },
    {
      title: 'Lead Age',
      key: 'age',
      width: 120,
      sorter: (a, b) => calculateLeadAge(a.created_at) - calculateLeadAge(b.created_at),
      render: (_, record) => {
        const age = calculateLeadAge(record.created_at);
        const color = age > 60 ? 'red' : age > 30 ? 'orange' : 'green';
        return (
          <Tag color={color} icon={<ClockCircleOutlined />}>
            {age} days
          </Tag>
        );
      }
    },
    {
      title: 'Last Updated',
      key: 'lastUpdated',
      width: 140,
      sorter: (a, b) => calculateDaysSinceUpdate(a.updated_at) - calculateDaysSinceUpdate(b.updated_at),
      render: (_, record) => {
        const days = calculateDaysSinceUpdate(record.updated_at);
        const isStale = days > 7;
        return (
          <Space>
            {isStale && <WarningOutlined style={{ color: '#f5222d' }} />}
            <Text type={isStale ? 'danger' : 'secondary'}>
              {days === 0 ? 'Today' : `${days} days ago`}
            </Text>
          </Space>
        );
      }
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 130,
      filters: statuses.map(s => ({ text: s, value: s })),
      onFilter: (value, record) => record.status === value,
      render: (status) => (
        <Tag color={statusColors[status] || 'default'}>{status}</Tag>
      )
    },
    {
      title: 'Enrolled Date',
      dataIndex: 'enrolled_at',
      key: 'enrolled_at',
      width: 130,
      sorter: (a, b) => dayjs(a.enrolled_at || 0).valueOf() - dayjs(b.enrolled_at || 0).valueOf(),
      render: (date, record) => (
        record.status === 'Enrolled'
          ? (date ? <Text>{dayjs(date).format('DD MMM YYYY')}</Text> : <Text type="secondary">—</Text>)
          : <Text type="secondary">—</Text>
      )
    },
    {
      title: 'Course',
      dataIndex: 'course_interested',
      key: 'course',
      width: 200,
      ellipsis: true,
      render: (text) => (
        <Tooltip title={text}>
          <Text ellipsis><BookOutlined /> {text}</Text>
        </Tooltip>
      )
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      width: 120,
      filters: countries.map(c => ({ text: c, value: c })),
      onFilter: (value, record) => record.country === value,
      render: (text) => (
        <Tag icon={<GlobalOutlined />}>{text}</Tag>
      )
    },
    {
      title: 'Assigned To',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
      width: 180,
      render: (assignedTo) => {
        const user = users.find(u => u.full_name === assignedTo);
        const displayName = user?.full_name || assignedTo;
        if (!displayName) return <Text type="secondary">Unassigned</Text>;
        return (
          <Space>
            <Avatar size="small" style={{ backgroundColor: '#722ed1' }}>
              {displayName?.charAt(0)?.toUpperCase()}
            </Avatar>
            <div>
              <div style={{ fontWeight: 500 }}>{displayName}</div>
              <Text type="secondary" style={{ fontSize: 12 }}>{user?.role}</Text>
            </div>
          </Space>
        );
      }
    },
    {
      title: 'Revenue',
      dataIndex: 'potential_revenue',
      key: 'revenue',
      width: 120,
      sorter: (a, b) => (a.potential_revenue || 0) - (b.potential_revenue || 0),
      render: (value) => (
        <Text strong style={{ color: '#52c41a' }}>
          ₹{Number(value || 0).toLocaleString('en-IN')}
        </Text>
      )
    },
    {
      title: 'Contact',
      key: 'contact',
      width: 150,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text ellipsis style={{ fontSize: 12 }}>{record.email}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.phone}</Text>
        </Space>
      )
    }
  ];

  // Shared pill renderer for user columns
  const pill = (n, bg, title, subset) => (
    <span
      title={n > 0 ? 'Click to view leads' : undefined}
      style={{ cursor: n > 0 ? 'pointer' : 'default', background: bg, color: '#fff', borderRadius: 12, padding: '2px 10px', fontWeight: 700, opacity: n === 0 ? 0.35 : 1 }}
      onClick={() => n > 0 && openDrawer(title, subset)}
    >{n}</span>
  );

  // User performance columns
  const userColumns = [
    {
      title: 'Rank',
      key: 'rank',
      width: 65,
      render: (_, __, i) => {
        if (i === 0) return <TrophyOutlined style={{ fontSize: 22, color: '#ffd700' }} />;
        if (i === 1) return <TrophyOutlined style={{ fontSize: 22, color: '#c0c0c0' }} />;
        if (i === 2) return <TrophyOutlined style={{ fontSize: 22, color: '#cd7f32' }} />;
        return <Text strong>#{i + 1}</Text>;
      },
    },
    {
      title: 'User',
      key: 'user',
      fixed: 'left',
      width: 180,
      render: (_, r) => (
        <Space>
          <Avatar style={{ backgroundColor: '#722ed1' }}>{r.userName?.charAt(0)?.toUpperCase()}</Avatar>
          <div>
            <div style={{ fontWeight: 500 }}>{r.userName}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>{r.userRole}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Total',
      dataIndex: 'totalLeads',
      key: 'totalLeads',
      width: 75,
      sorter: (a, b) => a.totalLeads - b.totalLeads,
      render: (n, r) => pill(n, '#1d4ed8', `${r.userName} — All Leads`, filteredLeads.filter(l => l.assigned_to === r.userId)),
    },
    {
      title: 'Fresh',
      dataIndex: 'fresh',
      key: 'fresh',
      width: 70,
      sorter: (a, b) => a.fresh - b.fresh,
      render: (n, r) => pill(n, '#0891b2', `${r.userName} — Fresh`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Fresh')),
    },
    {
      title: 'Follow Up',
      dataIndex: 'followUp',
      key: 'followUp',
      width: 90,
      sorter: (a, b) => a.followUp - b.followUp,
      render: (n, r) => pill(n, '#2563eb', `${r.userName} — Follow Up`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Follow Up')),
    },
    {
      title: 'Warm',
      dataIndex: 'warm',
      key: 'warm',
      width: 70,
      sorter: (a, b) => a.warm - b.warm,
      render: (n, r) => pill(n, '#d97706', `${r.userName} — Warm`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Warm')),
    },
    {
      title: 'Hot',
      dataIndex: 'hot',
      key: 'hot',
      width: 60,
      sorter: (a, b) => a.hot - b.hot,
      render: (n, r) => pill(n, '#dc2626', `${r.userName} — Hot`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Hot')),
    },
    {
      title: 'Enrolled',
      dataIndex: 'enrolled',
      key: 'enrolled',
      width: 80,
      sorter: (a, b) => a.enrolled - b.enrolled,
      render: (n, r) => pill(n, '#16a34a', `${r.userName} — Enrolled`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Enrolled')),
    },
    {
      title: 'Not Interested',
      dataIndex: 'notInterested',
      key: 'notInterested',
      width: 110,
      sorter: (a, b) => a.notInterested - b.notInterested,
      render: (n, r) => pill(n, '#6b7280', `${r.userName} — Not Interested`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Not Interested')),
    },
    {
      title: 'Not Answering',
      dataIndex: 'notAnswering',
      key: 'notAnswering',
      width: 110,
      sorter: (a, b) => a.notAnswering - b.notAnswering,
      render: (n, r) => pill(n, '#78716c', `${r.userName} — Not Answering`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Not Answering')),
    },
    {
      title: 'Junk',
      dataIndex: 'junk',
      key: 'junk',
      width: 65,
      sorter: (a, b) => a.junk - b.junk,
      render: (n, r) => pill(n, '#9ca3af', `${r.userName} — Junk`, filteredLeads.filter(l => l.assigned_to === r.userId && l.status === 'Junk')),
    },
    {
      title: 'Other',
      dataIndex: 'other',
      key: 'other',
      width: 65,
      sorter: (a, b) => a.other - b.other,
      render: (n, r) => pill(n, '#a855f7', `${r.userName} — Other`, filteredLeads.filter(l => l.assigned_to === r.userId && !['Fresh','Follow Up','Warm','Hot','Enrolled','Not Interested','Not Answering','Junk'].includes(l.status))),
    },
    {
      title: 'Stale >7d',
      dataIndex: 'staleLeads',
      key: 'staleLeads',
      width: 90,
      sorter: (a, b) => a.staleLeads - b.staleLeads,
      render: (n, r) => pill(n, '#f5222d', `${r.userName} — Stale (>7d)`, filteredLeads.filter(l => l.assigned_to === r.userId && calculateDaysSinceUpdate(l.updated_at) > 7)),
    },
    {
      title: 'Conv %',
      dataIndex: 'conversionRate',
      key: 'conversionRate',
      width: 80,
      sorter: (a, b) => parseFloat(a.conversionRate) - parseFloat(b.conversionRate),
      render: v => (
        <span style={{ color: v >= 30 ? '#16a34a' : v >= 15 ? '#d97706' : '#dc2626', fontWeight: 700 }}>
          {v}%
        </span>
      ),
    },
    {
      title: 'Avg Age',
      dataIndex: 'avgAge',
      key: 'avgAge',
      width: 90,
      sorter: (a, b) => parseFloat(a.avgAge) - parseFloat(b.avgAge),
      render: v => <Text>{v}d</Text>,
    },
    {
      title: 'Last Updated',
      dataIndex: 'avgDaysSinceUpdate',
      key: 'avgDaysSinceUpdate',
      width: 100,
      sorter: (a, b) => parseFloat(a.avgDaysSinceUpdate) - parseFloat(b.avgDaysSinceUpdate),
      render: v => <Text type={parseFloat(v) > 5 ? 'danger' : 'success'}>{v}d ago</Text>,
    },
    {
      title: 'Revenue',
      dataIndex: 'totalRevenue',
      key: 'totalRevenue',
      width: 130,
      sorter: (a, b) => a.totalRevenue - b.totalRevenue,
      render: (value) => (
        <Text strong style={{ color: '#52c41a' }}>
          ₹{Number(value || 0).toLocaleString('en-IN')}
        </Text>
      )
    }
  ];

  if (leadsLoading || usersLoading || coursesLoading) {
    return <div style={{ padding: 24, textAlign: 'center' }}>Loading...</div>;
  }

  return (
    <div style={{ padding: 24, background: '#f0f2f5', minHeight: '100vh' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>
            <RiseOutlined /> Lead Analysis Dashboard
          </Title>
          <Text type="secondary">Comprehensive lead insights and performance metrics</Text>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => refetchLeads()}>
              Refresh
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExport}>
              Export CSV ({filteredLeads.length})
            </Button>
            <Button icon={<FileExcelOutlined />} onClick={handleDownloadReport} style={{ color: '#16a34a', borderColor: '#16a34a' }}>
              Download Excel (.xlsx)
            </Button>
            <Button type="primary" icon={<FilePdfOutlined />} onClick={handleDownloadPDF} style={{ background: '#dc2626', borderColor: '#dc2626' }}>
              Download PDF Report
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Filters */}
      <Card style={{ marginBottom: 24 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <Text strong>Date Range</Text>
            <RangePicker
              value={dateRange}
              onChange={setDateRange}
              style={{ width: '100%', marginTop: 8 }}
              presets={[
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'days'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'days'), dayjs()] },
                { label: 'Last 90 Days', value: [dayjs().subtract(90, 'days'), dayjs()] },
                { label: 'Last 6 Months', value: [dayjs().subtract(6, 'months'), dayjs()] },
                { label: 'Last Year', value: [dayjs().subtract(1, 'year'), dayjs()] }
              ]}
            />
          </Col>
          <Col xs={24} sm={12} md={4}>
            <Text strong>Country</Text>
            <Select
              value={selectedCountry}
              onChange={setSelectedCountry}
              style={{ width: '100%', marginTop: 8 }}
            >
              <Option value="all">All Countries</Option>
              {countries.map(country => (
                <Option key={country} value={country}>{country}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={24} sm={12} md={4}>
            <Text strong>Course</Text>
            <Select
              value={selectedCourse}
              onChange={setSelectedCourse}
              style={{ width: '100%', marginTop: 8 }}
              showSearch
            >
              <Option value="all">All Courses</Option>
              {courseOptions.map(c => (
                <Option key={c} value={c}>{c}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={24} sm={12} md={4}>
            <Text strong>Status</Text>
            <Select
              value={selectedStatus}
              onChange={setSelectedStatus}
              style={{ width: '100%', marginTop: 8 }}
            >
              <Option value="all">All Statuses</Option>
              {statuses.map(status => (
                <Option key={status} value={status}>{status}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={24} sm={12} md={4}>
            <Text strong>Assigned To</Text>
            <Select
              value={selectedUser}
              onChange={setSelectedUser}
              style={{ width: '100%', marginTop: 8 }}
              showSearch
            >
              <Option value="all">All Users</Option>
              {users.map(user => (
                <Option key={user.id} value={user.full_name}>{user.full_name}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={24} sm={12} md={2}>
            <Text strong>Search</Text>
            <Input
              placeholder="Search..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </Col>
        </Row>
      </Card>

      {/* Key Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Total Leads"
              value={metrics.totalLeads || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Avg Lead Age"
              value={metrics.avgAge || 0}
              suffix="days"
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Avg Days Since Update"
              value={metrics.avgDaysSinceUpdate || 0}
              suffix="days"
              prefix={<ReloadOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Fresh Leads"
              value={metrics.freshLeads || 0}
              prefix={<CheckCircleOutlined />}
              suffix={`/ ${metrics.totalLeads || 0}`}
              valueStyle={{ color: '#52c41a' }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>Updated in last 2 days</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Stale Leads"
              value={metrics.staleLeads || 0}
              prefix={<WarningOutlined />}
              suffix={`(${metrics.staleRate || 0}%)`}
              valueStyle={{ color: '#f5222d' }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>Not updated in 7+ days</Text>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={4}>
          <Card>
            <Statistic
              title="Conversion Rate"
              value={metrics.conversionRate || 0}
              prefix={metrics.conversionRate >= 10 ? <RiseOutlined /> : <FallOutlined />}
              suffix="%"
              valueStyle={{ color: metrics.conversionRate >= 10 ? '#52c41a' : '#f5222d' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Tabs */}
      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="Overview Charts" key="overview">
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                <Card title="Lead Age Distribution">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={ageDistribution}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Bar dataKey="count" fill="#1890ff" name="Number of Leads" />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="Status Distribution">
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={statusDistribution}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {statusDistribution.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={statusColors[entry.name] || COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <RechartsTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="Top 10 Countries">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={countryDistribution} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="name" type="category" width={100} />
                      <RechartsTooltip />
                      <Bar dataKey="value" fill="#52c41a" name="Leads" />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="Top 10 Courses">
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={courseDistribution} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="name" type="category" width={150} />
                      <RechartsTooltip />
                      <Bar dataKey="value" fill="#722ed1" name="Leads" />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </Col>
              <Col xs={24}>
                <Card title="Lead Aging Analysis (Age vs Days Since Update)">
                  <ResponsiveContainer width="100%" height={400}>
                    <ScatterChart>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="age" name="Lead Age (days)" />
                      <YAxis dataKey="daysSinceUpdate" name="Days Since Update" />
                      <RechartsTooltip cursor={{ strokeDasharray: '3 3' }} />
                      <Legend />
                      <Scatter name="Leads" data={agingScatterData} fill="#1890ff" />
                    </ScatterChart>
                  </ResponsiveContainer>
                  <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                    Dots in the upper right indicate old leads that haven't been updated recently (require attention)
                  </Text>
                </Card>
              </Col>
            </Row>
          </TabPane>

          <TabPane tab="User Performance" key="performance">
            <Table
              columns={userColumns}
              dataSource={userPerformance}
              rowKey="userId"
              scroll={{ x: 1600 }}
              pagination={{ pageSize: 15, hideOnSinglePage: true }}
              size="small"
            />
          </TabPane>

          <TabPane tab="Detailed Leads" key="details">
            <Table
              columns={columns}
              dataSource={filteredLeads}
              rowKey="id"
              scroll={{ x: 1800 }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `Total ${total} leads` }}
            />
          </TabPane>
        </Tabs>
      </Card>

      {/* Leads drill-down drawer */}
      <Drawer
        title={drawer.title}
        open={drawer.open}
        onClose={() => setDrawer(d => ({ ...d, open: false }))}
        width={920}
        extra={<span style={{ color: '#6b7280', fontSize: 13 }}>{drawer.leads.length} leads</span>}
      >
        <Table
          dataSource={drawer.leads}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: t => `${t} leads` }}
          scroll={{ x: 800 }}
          columns={[
            { title: 'Name', dataIndex: 'full_name', key: 'name', width: 160, render: t => <strong>{t}</strong> },
            {
              title: 'Status',
              dataIndex: 'status',
              key: 'status',
              width: 130,
              render: s => {
                const c = { Fresh: 'cyan', 'Follow Up': 'blue', Warm: 'orange', Hot: 'red', Enrolled: 'green', 'Not Interested': 'default', 'Not Answering': 'default', Junk: 'default', 'Will Enroll Later': 'geekblue', Dropped: 'magenta', 'TMT No Response': 'gold', 'Re-assigned Lead': 'geekblue', 'Test Lead': 'default' };
                return <Tag color={c[s] || 'default'}>{s}</Tag>;
              },
            },
            { title: 'Source', dataIndex: 'source', key: 'source', width: 110 },
            { title: 'Country', dataIndex: 'country', key: 'country', width: 100 },
            { title: 'Course', dataIndex: 'course_interested', key: 'course', width: 200, ellipsis: true },
            { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 130 },
            { title: 'Email', dataIndex: 'email', key: 'email', width: 200, ellipsis: true },
            {
              title: 'Created',
              dataIndex: 'created_at',
              key: 'created',
              width: 110,
              render: v => v ? new Date(v).toLocaleDateString('en-IN') : '—',
            },
          ]}
        />
      </Drawer>
    </div>
  );
};

export default LeadAnalysisPage;
