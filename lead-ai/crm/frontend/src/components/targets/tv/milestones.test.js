import { milestoneFor, ordinal } from './milestones';

const c = (enrolled, revenue_pct) => ({ enrolled, revenue_pct });

test('ordinals', () => {
  expect([1, 2, 3, 4, 10, 11, 12, 13, 21, 22, 100].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '10th', '11th', '12th', '13th', '21st', '22nd', '100th']);
});

test('no banner for an ordinary sale', () => {
  expect(milestoneFor(c(6, 30), c(7, 33))).toBeNull();
});

test('every fifth enrollment is celebrated', () => {
  expect(milestoneFor(c(9, 30), c(10, 33)).text).toBe('10th enrollment this month!');
});

test('crossing a target quarter', () => {
  expect(milestoneFor(c(6, 48), c(7, 52)).text).toBe('Company crossed 50% of target');
});

test('hitting the target beats everything else, once', () => {
  expect(milestoneFor(c(9, 96), c(10, 101)).text).toBe('Company target reached!');
  expect(milestoneFor(c(10, 101), c(11, 105))).toBeNull();
});

test('missing data never throws', () => {
  expect(milestoneFor(null, c(1, 1))).toBeNull();
  expect(milestoneFor(c(1, null), c(2, null))).toBeNull();
});
